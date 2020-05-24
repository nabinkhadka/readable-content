# readable-content
Collects actual content of any article, blog, news, etc.

## Installation

`pip install readable-content`

## Usage

```
from readable_content.parser import ContentParser
parser = ContentParser("https://ideas.ted.com/how-do-animals-learn-how-to-be-well-animals-through-a-shared-culture/")
content = parser.get_content()
print(readable_content)
```
