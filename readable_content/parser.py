import math
import posixpath
import re
import urllib.parse
import urllib.request

from bs4 import BeautifulSoup
from lxml.html import fromstring


class ContentParser:
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
        self.input = html
        if html is None:
            self.input = urllib.request.urlopen(url).read().decode("utf-8")
        self.url = url
        self.input = self.regexps["replaceBrs"].sub("</p><p>", self.input)
        self.input = self.regexps["replaceFonts"].sub("<\g<1>span>", self.input)
        self.html = BeautifulSoup(self.input)
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
            unlikely_match_string = " ".join(elem.get("id", "")) + " ".join(
                elem.get("class", "")
            )

            if (
                self.regexps["unlikelyCandidates"].search(unlikely_match_string)
                and not self.regexps["okMaybeItsACandidate"].search(
                    unlikely_match_string
                )
                and elem.name != "body"
            ):
                elem.extract()
                continue

            if elem.name == "div":
                s = elem.renderContents().decode("utf-8")
                if not self.regexps["divToPElements"].search(s):
                    elem.name = "p"

        for node in self.html.findAll("p"):

            parent_node = node.parent
            grand_parent_node = parent_node.parent
            inner_text = node.text

            if not parent_node or len(inner_text) < 20:
                continue

            parent_hash = hash(str(parent_node))
            grand_parent_hash = hash(str(grand_parent_node))

            if parent_hash not in self.candidates:
                self.candidates[parent_hash] = self.initialize_node(parent_node)

            if grand_parent_node and grand_parent_hash not in self.candidates:
                self.candidates[grand_parent_hash] = self.initialize_node(
                    grand_parent_node
                )

            content_score = 1
            content_score += inner_text.count(",")
            content_score += inner_text.count(u"，")
            content_score += min(math.floor(len(inner_text) / 100), 3)

            self.candidates[parent_hash]["score"] += content_score
            if grand_parent_node:
                self.candidates[grand_parent_hash]["score"] += content_score / 2

        top_candidate = None

        for key in self.candidates:
            self.candidates[key]["score"] = self.candidates[key]["score"] * (
                1 - self.get_link_density(self.candidates[key]["node"])
            )

            if (
                not top_candidate
                or self.candidates[key]["score"] > top_candidate["score"]
            ):
                top_candidate = self.candidates[key]

        content = ""

        if top_candidate:
            content = top_candidate["node"]
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

        target_list = e.findAll(tag)
        is_embed = 0
        if tag == "object" or tag == "embed":
            is_embed = 1

        for target in target_list:
            attribute_values = ""
            for attribute in target.attrs:
                try:
                    # import pdb;pdb.set_trace()
                    attribute_values += target[attribute]
                except KeyError:
                    import pdb

                    pdb.set_trace()
                    print("")

            if is_embed and self.regexps["videos"].search(attribute_values):
                continue

            if is_embed and self.regexps["videos"].search(
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
        tags_list = e.findAll(tag)

        for node in tags_list:
            weight = self.get_class_weight(node)
            hash_node = hash(str(node))
            if hash_node in self.candidates:
                content_score = self.candidates[hash_node]["score"]
            else:
                content_score = 0

            if weight + content_score < 0:
                node.extract()
            else:
                p = len(node.findAll("p"))
                img = len(node.findAll("img"))
                li = len(node.findAll("li")) - 100
                input = len(node.findAll("input"))
                embed_count = 0
                embeds = node.findAll("embed")
                for embed in embeds:
                    if not self.regexps["videos"].search(embed["src"]):
                        embed_count += 1
                link_density = self.get_link_density(node)
                content_length = len(node.text)
                to_remove = False

                if img > p:
                    to_remove = True
                elif li > p and tag != "ul" and tag != "ol":
                    to_remove = True
                elif input > math.floor(p / 3):
                    to_remove = True
                elif content_length < 25 and (img == 0 or img > 2):
                    to_remove = True
                elif weight < 25 and link_density > 0.2:
                    to_remove = True
                elif weight >= 25 and link_density > 0.5:
                    to_remove = True
                elif (embed_count == 1 and content_length < 35) or embed_count > 1:
                    to_remove = True

                if to_remove:
                    node.extract()

    def get_article_title(self):
        title = ""
        try:
            title = self.html.find("title").text
        except:
            pass

        return title

    def initialize_node(self, node):
        content_score = 0

        if node.name == "div":
            content_score += 5
        elif node.name == "blockquote":
            content_score += 3
        elif node.name == "form":
            content_score -= 3
        elif node.name == "th":
            content_score -= 5

        content_score += self.get_class_weight(node)

        return {"score": content_score, "node": node}

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
        text_length = len(node.text)

        if text_length == 0:
            return 0
        link_length = 0
        for link in links:
            link_length += len(link.text)

        return link_length / text_length

    def fix_images_path(self, node):
        imgs = node.findAll("img")
        for img in imgs:
            src = img.get("src", None)
            if not src:
                img.extract()
                continue

            if "http://" != src[:7] and "https://" != src[:8]:
                new_src = urllib.parse.urljoin(self.url, src)

                new_src_arr = urllib.parse.urlparse(new_src)
                new_path = posixpath.normpath(new_src_arr[2])
                new_src = urllib.parse.urlunparse(
                    (
                        new_src_arr.scheme,
                        new_src_arr.netloc,
                        new_path,
                        new_src_arr.params,
                        new_src_arr.query,
                        new_src_arr.fragment,
                    )
                )
                img["src"] = new_src


if __name__ == "__main__":
    p = ContentParser("https://ideas.ted.com/how-do-animals-learn-how-to-be-well-animals-through-a-shared-culture/")
    content = p.get_content()
    print(content)
