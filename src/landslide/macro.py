# -*- coding: utf-8 -*-

#  Copyright 2010 Adam Zapletal
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

import os
import re
import htmlentitydefs
import pygments
import sys
import utils

from pygments.lexers import get_lexer_by_name
from pygments.formatters import HtmlFormatter


class Macro(object):
    """Base class for Macros. A Macro aims to analyse, process and eventually
       alter some provided HTML contents and to provide supplementary
       informations to the slide context.
    """
    options = {}

    def __init__(self, logger=sys.stdout, embed=False, options=None):
        self.logger = logger
        self.embed = embed
        if options:
            if not isinstance(options, dict):
                raise ValueError(u'Macro options must be a dict instance')
            self.options = options

    def process(self, content, source=None):
        """Generic processor (does actually nothing)"""
        return content, []


class CodeHighlightingMacro(Macro):
    """This Macro performs syntax coloration in slide code blocks using
       Pygments.
    """
    banged_blocks_re = re.compile(r"""
        (?P<block>
            <pre.+?>
            (<code>)?
            \s?
            (?P<pound> [#]? )
            [!]+
            (?P<lang> \w+? )\n
            (?P<code> .*? )
            (</code>)?
            </pre>
        )
        """, re.VERBOSE | re.UNICODE | re.MULTILINE | re.DOTALL)
    fenced_blocks_re = re.compile(r"""
        (?P<block>
            <pre>
            <code
                \s+class=
                (?P<q> ["'] )
                (?P<pound> [#]? )
                (?P<lang> \w+? )
                (?P=q)
            >
            (?P<code> .*? )
            (</code>)?</pre>
        )
        """, re.VERBOSE | re.UNICODE | re.MULTILINE | re.DOTALL)

    html_entity_re = re.compile('&(\w+?);')

    def descape(self, string, defs=None):
        """Decodes html entities from a given string"""
        if defs is None:
            defs = htmlentitydefs.entitydefs
        f = lambda m: defs[m.group(1)] if len(m.groups()) > 0 else m.group(0)
        return self.html_entity_re.sub(f, string)

    def pygmentize(self, content, match, has_linenos=False):
        block, lang, code = match.group('block'), match.group('lang'), match.group('code')
        try:
            lexer = get_lexer_by_name(lang)
        except Exception:
            self.logger(u"Unknown pygment lexer \"%s\", skipping"
                        % lang, 'warning')
            return content

        has_linenos = self.options['linenos'] if not match.group('pound') else True

        formatter = HtmlFormatter(linenos=has_linenos,
                                    nobackground=True)
        pretty_code = pygments.highlight(self.descape(code), lexer,
                                            formatter)
        return content.replace(block, pretty_code, 1)

    def process(self, content, source=None):
        if 'linenos' not in self.options or self.options['linenos'] =='no':
            self.options['linenos'] = False
        classes = []
        for block_re in (self.banged_blocks_re, self.fenced_blocks_re):
            blocks = block_re.finditer(content)
            if not blocks:
                continue
            classes = [u'has_code']
            for match in blocks:
                content = self.pygmentize(content, match)

        return content, classes


class EmbedImagesMacro(Macro):
    """This Macro extracts images url and embed them using the base64
       algorithm.
    """
    def process(self, content, source=None):
        classes = []

        if not self.embed:
            return content, classes

        images = re.findall(r'<img\s.*?src="(.+?)"\s?.*?/?>', content,
                            re.DOTALL | re.UNICODE)

        source_dir = os.path.dirname(source)

        for image_url in images:
            encoded_url = utils.encode_image_from_url(image_url, source_dir)

            if not encoded_url:
                self.logger(u"Failed to embed image \"%s\"" % image_url, 'warning')
                return content, classes

            content = content.replace(u"src=\"" + image_url,
                                      u"src=\"" + encoded_url, 1)

            self.logger(u"Embedded image %s" % image_url, 'notice')

        return content, classes


class FixImagePathsMacro(Macro):
    """This Macro replaces html image paths with fully qualified absolute
       urls.
    """
    relative = False

    def process(self, content, source=None):
        classes = []

        if self.embed:
            return content, classes
        base_path = utils.get_path_url(source, self.options.get('relative'))
        base_url = os.path.split(base_path)[0]

        images = re.findall(r'<img.*?src="(?!http://)(.*?)".*/?>', content,
            re.DOTALL | re.UNICODE)

        for image in images:
            full_path = os.path.join(base_url, image)

            content = content.replace(image, full_path)

        return content, classes


class FxMacro(Macro):
    """This Macro processes fx directives, ie adds specific css classes
       named after what the parser found in them.
    """
    def process(self, content, source=None):
        classes = []

        fx_match = re.search(r'(<p>\.fx:\s?(.*?)</p>\n?)', content,
                             re.DOTALL | re.UNICODE)
        if fx_match:
            classes = fx_match.group(2).split(u' ')
            content = content.replace(fx_match.group(1), '', 1)

        return content, classes


class NotesMacro(Macro):
    """This Macro processes Notes."""
    def process(self, content, source=None):
        classes = []

        new_content = re.sub(r'<p>\.notes:\s?(.*?)</p>',
                             r'<p class="notes">\1</p>', content)

        if content != new_content:
            classes.append(u'has_notes')

        return new_content, classes


class QRMacro(Macro):
    """This Macro generates a QR Code with Google Chart API."""
    def process(self, content, source=None):
        classes = []

        new_content = re.sub(r'<p>\.qr:\s?(\d*?)\|(.*?)</p>',
                             r'<p class="qr"><img src="http://chart.apis.google.com/chart?chs=\1x\1&cht=qr&chl=\2&chf=bg,s,00000000&choe=UTF-8" alt="QR Code" /></p>',
                             content)

        if content != new_content:
            classes.append(u'has_qr')

        return new_content, classes
