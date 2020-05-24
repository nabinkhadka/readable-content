# coding=utf-8

from __future__ import division
import os
import sys
import urllib.request
import urllib.parse
import re
from html.parser import HTMLParser
import math
from lxml.html import fromstring
import posixpath

import chardet
from bs4 import BeautifulSoup


class ReadableContentParser:

    regexps = {
        "unlikelyCandidates": re.compile(
            "combx|comment|community|disqus|extra|foot|header|menu|"
            "remark|rss|shoutbox|sidebar|sponsor|ad-break|agegate|"
            "pagination|pager|popup|tweet|twitter",
            re.I,
        ),
        "okMaybeItsACandidate": re.compile("and|article|body|column|main|shadow", re.I),
        "positive": re.compile(
            "article|body|content|entry|hentry|main|page|pagination|post|text|"
            "blog|story",
            re.I,
        ),
        "negative": re.compile(
            "combx|comment|com|contact|foot|footer|footnote|masthead|media|"
            "meta|outbrain|promo|related|scroll|shoutbox|sidebar|sponsor|"
            "shopping|tags|tool|widget",
            re.I,
        ),
        "extraneous": re.compile(
            "print|archive|comment|discuss|e[\-]?mail|share|reply|all|login|"
            "sign|single",
            re.I,
        ),
        "divToPElements": re.compile(
            "<(a|blockquote|dl|div|img|ol|p|pre|table|ul)", re.I
        ),
        "replaceBrs": re.compile("(<br[^>]*>[ \n\r\t]*){2,}", re.I),
        "replaceFonts": re.compile("<(/?)font[^>]*>", re.I),
        "trim": re.compile("^\s+|\s+$", re.I),
        "normalize": re.compile("\s{2,}", re.I),
        "killBreaks": re.compile("(<br\s*/?>(\s|&nbsp;?)*)+", re.I),
        "videos": re.compile("http://(www\.)?(youtube|vimeo)\.com", re.I),
        "skipFootnoteLink": re.compile(
            "^\s*(\[?[a-z0-9]{1,2}\]?|^|edit|citation needed)\s*$", re.I
        ),
        "nextLink": re.compile("(next|weiter|continue|>([^\|]|$)|»([^\|]|$))", re.I),
        "prevLink": re.compile("(prev|earl|old|new|<|«)", re.I),
    }

    def __init__(self, url, html=None):
        self.candidates = {}
        if html is None:
            input = urllib.request.urlopen(url).read().decode("utf-8")
        else:
            input = html
        self.input = input
        self.url = url
        self.input = self.regexps["replaceBrs"].sub("</p><p>", self.input)
        self.input = self.regexps["replaceFonts"].sub("<\g<1>span>", self.input)
        self.html = BeautifulSoup(self.input)

        #        print self.html.originalEncoding
        #        print self.html
        self.remove_script()
        self.remove_style()
        self.remove_link()

        self.title = self.get_article_title()
        self.content = self.grab_article()

    def get_content(self):
        response = fromstring(self.content)
        content = ""
        for i in response.iterdescendants():
            content += "".join([each.strip() for each in i.xpath("text()")])
        return content

    def remove_script(self):
        for elem in self.html.findAll("script"):
            elem.decompose()

    def remove_style(self):
        for elem in self.html.findAll("style"):
            elem.decompose()

    def remove_link(self):
        for elem in self.html.findAll("link"):
            elem.decompose()

    def grab_article(self):

        for elem in self.html.findAll(True):
            # import pdb; pdb.set_trace()
            unlikelyMatchString = " ".join(elem.get("id", "")) + " ".join(
                elem.get("class", "")
            )

            if (
                self.regexps["unlikelyCandidates"].search(unlikelyMatchString)
                and not self.regexps["okMaybeItsACandidate"].search(unlikelyMatchString)
                and elem.name != "body"
            ):
                #                print elem
                #                print '--------------------'
                elem.extract()
                continue
            #                pass

            if elem.name == "div":
                s = elem.renderContents().decode("utf-8")
                # import pdb; pdb.set_trace()
                if not self.regexps["divToPElements"].search(s):
                    elem.name = "p"

        for node in self.html.findAll("p"):

            parentNode = node.parent
            grandParentNode = parentNode.parent
            innerText = node.text

            #            print '=================='
            #            print node
            #            print '------------------'
            #            print parentNode

            if not parentNode or len(innerText) < 20:
                continue

            parentHash = hash(str(parentNode))
            grandParentHash = hash(str(grandParentNode))

            if parentHash not in self.candidates:
                self.candidates[parentHash] = self.initialize_node(parentNode)

            if grandParentNode and grandParentHash not in self.candidates:
                self.candidates[grandParentHash] = self.initialize_node(grandParentNode)

            contentScore = 1
            contentScore += innerText.count(",")
            contentScore += innerText.count(u"，")
            contentScore += min(math.floor(len(innerText) / 100), 3)

            self.candidates[parentHash]["score"] += contentScore

            #            print '======================='
            #            print self.candidates[parentHash]['score']
            #            print self.candidates[parentHash]['node']
            #            print '-----------------------'
            #            print node

            if grandParentNode:
                self.candidates[grandParentHash]["score"] += contentScore / 2

        topCandidate = None

        for key in self.candidates:
            #            print '======================='
            #            print self.candidates[key]['score']
            #            print self.candidates[key]['node']

            self.candidates[key]["score"] = self.candidates[key]["score"] * (
                1 - self.get_link_density(self.candidates[key]["node"])
            )

            if (
                not topCandidate
                or self.candidates[key]["score"] > topCandidate["score"]
            ):
                topCandidate = self.candidates[key]

        content = ""

        if topCandidate:
            content = topCandidate["node"]
            #            print content
            content = self.clean_article(content)
        return content

    def clean_article(self, content):

        self.clean_style(content)
        self.clean(content, "h1")
        self.clean(content, "object")
        self.clean_conditionally(content, "form")

        if len(content.findAll("h2")) == 1:
            self.clean(content, "h2")

        self.clean(content, "iframe")

        self.clean_conditionally(content, "table")
        self.clean_conditionally(content, "ul")
        self.clean_conditionally(content, "div")

        self.fix_images_path(content)

        content = content.renderContents().decode("utf-8")
        content = self.regexps["killBreaks"].sub("<br />", content)

        return content

    def clean(self, e, tag):

        targetList = e.findAll(tag)
        isEmbed = 0
        if tag == "object" or tag == "embed":
            isEmbed = 1

        for target in targetList:
            attributeValues = ""
            for attribute in target.attrs:
                try:
                    # import pdb;pdb.set_trace()
                    attributeValues += target[attribute]
                except KeyError:
                    import pdb

                    pdb.set_trace()
                    print("")

            if isEmbed and self.regexps["videos"].search(attributeValues):
                continue

            if isEmbed and self.regexps["videos"].search(
                target.renderContents(encoding=None)
            ):
                continue
            target.extract()

    def clean_style(self, e):

        for elem in e.findAll(True):
            del elem["class"]
            del elem["id"]
            del elem["style"]

    def clean_conditionally(self, e, tag):
        tagsList = e.findAll(tag)

        for node in tagsList:
            weight = self.get_class_weight(node)
            hashNode = hash(str(node))
            if hashNode in self.candidates:
                contentScore = self.candidates[hashNode]["score"]
            else:
                contentScore = 0

            if weight + contentScore < 0:
                node.extract()
            else:
                p = len(node.findAll("p"))
                img = len(node.findAll("img"))
                li = len(node.findAll("li")) - 100
                input = len(node.findAll("input"))
                embedCount = 0
                embeds = node.findAll("embed")
                for embed in embeds:
                    if not self.regexps["videos"].search(embed["src"]):
                        embedCount += 1
                linkDensity = self.get_link_density(node)
                contentLength = len(node.text)
                toRemove = False

                if img > p:
                    toRemove = True
                elif li > p and tag != "ul" and tag != "ol":
                    toRemove = True
                elif input > math.floor(p / 3):
                    toRemove = True
                elif contentLength < 25 and (img == 0 or img > 2):
                    toRemove = True
                elif weight < 25 and linkDensity > 0.2:
                    toRemove = True
                elif weight >= 25 and linkDensity > 0.5:
                    toRemove = True
                elif (embedCount == 1 and contentLength < 35) or embedCount > 1:
                    toRemove = True

                if toRemove:
                    node.extract()

    def get_article_title(self):
        title = ""
        try:
            title = self.html.find("title").text
        except:
            pass

        return title

    def initialize_node(self, node):
        contentScore = 0

        if node.name == "div":
            contentScore += 5
        elif node.name == "blockquote":
            contentScore += 3
        elif node.name == "form":
            contentScore -= 3
        elif node.name == "th":
            contentScore -= 5

        contentScore += self.get_class_weight(node)

        return {"score": contentScore, "node": node}

    def get_class_weight(self, node):
        weight = 0
        if "class" in node:
            if self.regexps["negative"].search(node["class"]):
                weight -= 25
            if self.regexps["positive"].search(node["class"]):
                weight += 25

        if "id" in node:
            if self.regexps["negative"].search(node["id"]):
                weight -= 25
            if self.regexps["positive"].search(node["id"]):
                weight += 25

        return weight

    def get_link_density(self, node):
        links = node.findAll("a")
        textLength = len(node.text)

        if textLength == 0:
            return 0
        linkLength = 0
        for link in links:
            linkLength += len(link.text)

        return linkLength / textLength

    def fix_images_path(self, node):
        imgs = node.findAll("img")
        for img in imgs:
            src = img.get("src", None)
            if not src:
                img.extract()
                continue

            if "http://" != src[:7] and "https://" != src[:8]:
                newSrc = urllib.parse.urljoin(self.url, src)

                newSrcArr = urllib.parse.urlparse(newSrc)
                newPath = posixpath.normpath(newSrcArr[2])
                newSrc = urllib.parse.urlunparse(
                    (
                        newSrcArr.scheme,
                        newSrcArr.netloc,
                        newPath,
                        newSrcArr.params,
                        newSrcArr.query,
                        newSrcArr.fragment,
                    )
                )
                img["src"] = newSrc
