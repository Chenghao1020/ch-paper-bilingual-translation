"""Render explicitly reviewed LaTeX annotations as offline native MathML."""
from functools import lru_cache
import html
from pathlib import Path
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET

VENDOR = Path(__file__).resolve().parent / 'vendor'
sys.path.insert(0, str(VENDOR))
from latex2mathml.converter import convert

NAMESPACE = 'http://www.w3.org/1998/Math/MathML'
ET.register_namespace('', NAMESPACE)
MATH_TAGS = {'math', 'mrow', 'mi', 'mn', 'mo', 'mtext', 'mspace', 'ms', 'mfrac',
             'msqrt', 'mroot', 'mstyle', 'merror', 'mpadded', 'mphantom', 'mfenced',
             'menclose', 'msub', 'msup', 'msubsup', 'munder', 'mover', 'munderover',
             'mmultiscripts', 'mprescripts', 'none', 'mtable', 'mtr', 'mlabeledtr',
             'mtd', 'semantics', 'annotation'}

STYLE_EXCEPTIONS = {
    'script': dict(zip('BEFHILReg o'.replace(' ', ''), 'ℬℰℱℋℐℒℛℯℊℴ')),
    'double-struck': dict(zip('CHNPQRZ', 'ℂℍℕℙℚℝℤ')),
    'fraktur': dict(zip('CHIRZ', 'ℭℌℑℜℨ')),
    'italic': {'h': 'ℎ'},
}


def styled_letter(char, variant):
    if char in STYLE_EXCEPTIONS.get(variant, {}):
        return STYLE_EXCEPTIONS[variant][char]
    name = unicodedata.name(char, '')
    if name.startswith('LATIN '):
        name = name.replace('LATIN ', '').replace(' LETTER ', ' ')
    elif name.startswith('GREEK '):
        name = name.replace('GREEK ', '').replace(' LETTER ', ' ')
    elif not name.startswith('DIGIT '):
        return char
    try:
        return unicodedata.lookup('MATHEMATICAL ' + variant.upper() + ' ' + name)
    except KeyError:
        return char


def preserve_math_fonts(node, inherited='normal'):
    # MathML Core browsers support mathvariant=normal; encode other variants
    # as actual mathematical alphabet characters rather than losing meaning.
    variant = node.get('mathvariant', inherited)
    if node.tag.split('}', 1)[1] in ('mi', 'mn') and node.text and variant != 'normal':
        node.text = ''.join(styled_letter(char, variant) for char in node.text)
        node.set('mathvariant', 'normal')
    for child in node:
        preserve_math_fonts(child, variant)


def mathml(latex, display='inline'):
    if not isinstance(latex, str) or not latex.strip():
        raise ValueError('LaTeX must be a nonempty string')
    return _mathml(latex, display)


@lru_cache(maxsize=4096)
def _mathml(latex, display):
    if len(latex) > 20000:
        raise ValueError('Split excessively long equations into readable rows')
    # No file/network/HTML commands or custom macro definitions in paper math.
    if re.search(r'\\(?:href|url|includegraphics|input|include|write|def|newcommand|renewcommand|html\w*)\b', latex):
        raise ValueError('Unsupported external or executable LaTeX command')
    try:
        normalized = re.sub(r'\\begin\{(?:aligned|split)\}', r'\\begin{array}{rl}', latex)
        normalized = re.sub(r'\\end\{(?:aligned|split)\}', r'\\end{array}', normalized)
        root = ET.fromstring(convert(normalized, display=display))
    except Exception as error:
        raise ValueError('Cannot render LaTeX; check the transcribed equation') from error
    for node in root.iter():
        if node.text and re.search(r'\\[A-Za-z]+', node.text):
            raise ValueError('Unsupported LaTeX command; use supported standard math notation')
        if not node.tag.startswith('{' + NAMESPACE + '}') or node.tag.split('}', 1)[1] not in MATH_TAGS:
            raise ValueError('Non-MathML markup is not allowed')
        for attribute in list(node.attrib):
            if attribute.lower().startswith('on') or attribute.lower() in ('href', 'src', 'style') or 'href' in attribute.lower():
                raise ValueError('Unsafe MathML attribute')
    root.set('aria-label', latex)
    root.set('class', 'paper-math')
    preserve_math_fonts(root)
    return ET.tostring(root, encoding='unicode')


def math_errors(record):
    errors = []
    metadata = record.get('math', {})
    if not isinstance(metadata, dict):
        return ['math annotations must be an object']
    if metadata and metadata.get('reviewed') is not True:
        errors.append('math annotations have not been reviewed')
    for side in ('source', 'target'):
        annotations = metadata.get(side, [])
        if not isinstance(annotations, list):
            errors.append(f'math {side} annotations must be a list')
            continue
        spans = set()
        for item in annotations:
            if not isinstance(item, dict) or not isinstance(item.get('text'), str) or not item['text']:
                errors.append('math annotation must provide original text')
                continue
            token = item['text']
            if token not in record.get(side, ''):
                errors.append(f'math {side} text does not occur in original content')
            if token in spans:
                errors.append(f'duplicate math {side} annotation')
            spans.add(token)
            if record.get('alignment') and not any(token in unit for unit in record['alignment'][side]):
                errors.append(f'math {side} annotation crosses sentence boundaries')
            try:
                mathml(item.get('latex'))
            except ValueError as error:
                errors.append(str(error))
    rows = record.get('equations', [])
    if record.get('kind') == 'equation' and not rows:
        errors.append('typeset equation rows are missing')
    if rows:
        if not isinstance(rows, list):
            return errors + ['equations must be a list']
        if record.get('math_reviewed') is not True:
            errors.append('equation transcription has not been reviewed')
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get('label', ''), str):
                errors.append('invalid equation row')
                continue
            try:
                mathml(row.get('latex'), 'block')
            except ValueError as error:
                errors.append(str(error))
    return errors


def text_parts(text, record, side):
    annotations = record.get('math', {}).get(side, [])
    if not annotations:
        return [(text, None)]
    by_text = {item['text']: item['latex'] for item in annotations}
    pattern = re.compile('|'.join(re.escape(token) for token in sorted(by_text, key=len, reverse=True)))
    parts, cursor = [], 0
    for match in pattern.finditer(text):
        if match.start() > cursor:
            parts.append((text[cursor:match.start()], None))
        parts.append((match.group(), by_text[match.group()]))
        cursor = match.end()
    parts.append((text[cursor:], None))
    return parts


def render_text(text, record=None, side='source'):
    record = record or {}
    parts = []
    for original, latex in text_parts(str(text), record, side):
        if latex is None:
            parts.append('<br>'.join(html.escape(original).split('\n')))
        else:
            parts.append(f'<span class="math-inline" data-original="{html.escape(original, quote=True)}">{mathml(latex)}</span>')
    return ''.join(parts)


def markdown_text(text, record=None, side='source'):
    return ''.join('$' + latex + '$' if latex is not None else original.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                   for original, latex in text_parts(str(text), record or {}, side))


def render_equations(record):
    rows = []
    for row in record.get('equations', []):
        label = html.escape(row.get('label', ''))
        rows.append(f'<div class="equation-row"><div class="equation-scroll">{mathml(row["latex"], "block")}</div><span class="equation-number">{label}</span></div>')
    return '<div class="typeset-equations">' + ''.join(rows) + '</div>'


def markdown_equations(record):
    rows = []
    for row in record.get('equations', []):
        label = row.get('label', '').strip('() ')
        tag = r'\tag{' + label + '}' if label else ''
        rows.append('$$\n' + row['latex'] + tag + '\n$$\n')
    return '\n'.join(rows)
