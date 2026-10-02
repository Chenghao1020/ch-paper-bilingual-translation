"""Reusable local PDF preparation and bilingual HTML/Markdown publishing.

Translation is authored by the calling agent in records.json, not synthesized
by this script. No API calls, credentials, or paper-specific constants.
"""
import argparse
import base64
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from collections import Counter

SKILL = Path(__file__).resolve().parents[1]
KINDS = {'title', 'heading', 'paragraph', 'equation', 'figure', 'table', 'reference'}


def contained(root, value):
    root = Path(root).resolve()
    path = (root / value).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f'Path escapes permitted directory: {path}')
    return path


def basename(value):
    if not value or re.search(r'[<>:"/\\|?*\x00-\x1f]', value) or value.endswith((' ', '.')):
        raise ValueError(f'Invalid filename component: {value!r}')
    if value in ('.', '..') or re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', value, re.I):
        raise ValueError('Reserved filename')
    return value


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def environment(workspace):
    temp = contained(workspace, 'tmp/paper-translation')
    temp.mkdir(parents=True, exist_ok=True)
    for key in ('TEMP', 'TMP', 'TMPDIR'):
        os.environ[key] = str(temp)
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'


def poppler(name, directory=None):
    exe = name + ('.exe' if os.name == 'nt' else '')
    path = Path(directory) / exe if directory else None
    if path is None:
        found = shutil.which(exe)
        if found:
            path = Path(found)
    if path is None or not path.is_file():
        raise ValueError(f'{name} unavailable; pass --poppler-bin from the workspace runtime.')
    return path


def init(args):
    workspace = Path(args.workspace).resolve(strict=True)
    environment(workspace)
    name = basename(args.name)
    job = contained(workspace, f'analysis/paper-translations/{name}')
    if job.exists():
        raise ValueError(f'Job already exists: {job}; resume it or use a new name.')
    src = Path(args.pdf).resolve(strict=True)
    if not src.is_file():
        raise ValueError('Source PDF must be a file')
    from pypdf import PdfReader
    reader = PdfReader(src)
    if reader.is_encrypted and not reader.decrypt(''):
        raise ValueError('PDF is encrypted; obtain an accessible source.')
    render = poppler('pdftoppm', args.poppler_bin) if args.render else None
    job.mkdir(parents=True)
    source = contained(job, 'source.pdf')
    shutil.copyfile(src, source)
    pages = []
    text_parts = []
    for number, page in enumerate(reader.pages, 1):
        text = page.extract_text(extraction_mode='layout') or ''
        links = []
        for annotation in page.get('/Annots', []):
            obj = annotation.get_object()
            uri = obj.get('/A', {}).get('/URI')
            if uri:
                links.append({'uri': str(uri), 'rect': [float(v) for v in obj.get('/Rect', [])]})
        pages.append({'page': number, 'width_pt': float(page.mediabox.width),
                      'height_pt': float(page.mediabox.height), 'text': text,
                      'needs_ocr_or_visual_reading': len(re.findall(r'\w', text)) < 30,
                      'links': links})
        text_parts.append(f'\n===== PAGE {number} =====\n{text}\n')
    save(contained(job, 'source_pages.json'), pages)
    contained(job, 'source_text.txt').write_text(''.join(text_parts), encoding='utf-8')
    save(contained(job, 'records.json'), [])
    manifest = {
        'schema_version': 1, 'workspace': str(workspace), 'source_pdf': 'source.pdf',
        'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'page_count': len(pages), 'title': {'source': src.stem, 'target': ''},
        'languages': {'source': {'code': 'en', 'label': 'English'},
                      'target': {'code': 'zh-CN', 'label': '中文'}},
        'records_file': 'records.json', 'output_prefix': name + '_论文中英对照',
        'expected_ids': [], 'glossary': [], 'editorial_notes': [],
        'review': {'reading_order': False, 'translation_complete': False,
                   'formulas_tables': False, 'visual_assets': False},
    }
    save(contained(job, 'paper.json'), manifest)
    if render:
        render_pages(job, manifest, render, args.dpi)
    print(json.dumps({'job': str(job), 'pages': len(pages),
                      'visual_reading_pages': [x['page'] for x in pages if x['needs_ocr_or_visual_reading']]}, ensure_ascii=False))


def render_pages(job, manifest, executable, dpi):
    if not 72 <= dpi <= 400:
        raise ValueError('DPI must be between 72 and 400')
    target = contained(job, 'pages')
    target.mkdir(exist_ok=True)
    for number in range(1, manifest['page_count'] + 1):
        output = contained(target, f'page-{number:03d}')
        subprocess.run([str(executable), '-f', str(number), '-l', str(number),
                        '-singlefile', '-r', str(dpi), '-png',
                        str(contained(job, manifest['source_pdf'])), str(output)],
                       cwd=job, check=True, capture_output=True)


def get_job(args):
    job = Path(args.job).resolve(strict=True)
    manifest = load(job / 'paper.json')
    workspace = Path(manifest['workspace']).resolve(strict=True)
    if not job.is_relative_to(workspace):
        raise ValueError('Job must be inside its configured workspace')
    environment(workspace)
    return job, manifest, workspace


def render(args):
    job, manifest, _ = get_job(args)
    render_pages(job, manifest, poppler('pdftoppm', args.poppler_bin), args.dpi)
    print('Source pages rendered.')


def alignment_errors(record):
    alignment = record.get('alignment')
    if alignment is None:
        return ['sentence alignment is missing'] if record.get('kind') in ('paragraph', 'figure') else []
    if not isinstance(alignment, dict):
        return ['sentence alignment must be an object']
    errors = []
    for side in ('source', 'target'):
        units = alignment.get(side)
        if not isinstance(units, list) or not units or any(not isinstance(s, str) or not s.strip() for s in units):
            errors.append(f'alignment {side} must contain nonempty text units')
        elif ''.join(units) != record.get(side):
            errors.append(f'alignment {side} must reproduce the exact original text')
    if errors:
        return errors
    pairs = alignment.get('pairs')
    if not isinstance(pairs, list) or not pairs:
        return ['alignment pairs must be a nonempty index list']
    valid = []
    for pair in pairs:
        if (not isinstance(pair, list) or len(pair) != 2 or
                any(type(i) is not int for i in pair) or
                not 0 <= pair[0] < len(alignment['source']) or
                not 0 <= pair[1] < len(alignment['target'])):
            errors.append('invalid sentence pair indices')
        else:
            valid.append(tuple(pair))
    if len(valid) != len(set(valid)):
        errors.append('duplicate sentence pairs')
    for column, side in enumerate(('source', 'target')):
        unpaired = alignment.get('unpaired_' + side, [])
        if (not isinstance(unpaired, list) or any(type(i) is not int or not 0 <= i < len(alignment[side]) for i in unpaired)):
            errors.append(f'invalid unpaired {side} indices')
            continue
        covered = {pair[column] for pair in valid}
        if covered.intersection(unpaired) or len(unpaired) != len(set(unpaired)):
            errors.append(f'conflicting unpaired {side} indices')
        if covered.union(unpaired) != set(range(len(alignment[side]))):
            errors.append(f'alignment {side} coverage is incomplete')
    if alignment.get('reviewed') is not True:
        errors.append('sentence alignment has not been reviewed')
    return errors


def validate(job, manifest, records, draft=False):
    problems, warnings = [], []
    if manifest.get('schema_version') != 1:
        problems.append('Unsupported schema_version')
    try:
        basename(manifest.get('output_prefix', ''))
    except ValueError as e:
        problems.append(str(e))
    if not records:
        problems.append('No bilingual records')
    if not manifest.get('title', {}).get('target'):
        problems.append('Target title is empty')
    ids = []
    count = manifest.get('page_count', 0)
    for r in records:
        rid = r.get('id', '')
        ids.append(rid)
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*', rid):
            problems.append(f'Invalid record ID: {rid!r}')
        if r.get('kind') not in KINDS:
            problems.append(f'{rid}: unknown kind')
        if not isinstance(r.get('source'), str) or not r['source'].strip():
            problems.append(f'{rid}: source text is missing')
        if r.get('kind') != 'equation' and (not isinstance(r.get('target'), str) or not r['target'].strip()):
            problems.append(f'{rid}: target text is missing')
        if not isinstance(r.get('target', ''), str):
            problems.append(f'{rid}: target text must be a string')
        pages = r.get('pages', [])
        if not isinstance(pages, list) or not pages or any(type(p) is not int or not 1 <= p <= count for p in pages):
            problems.append(f'{rid}: invalid source pages')
        if r.get('kind') == 'heading' and r.get('level') not in (1, 2, 3):
            problems.append(f'{rid}: heading level must be 1, 2, or 3')
        problems.extend(f'{rid}: {error}' for error in alignment_errors(r))
        for asset in r.get('visuals', []):
            page = asset.get('page')
            if type(page) is not int or not 1 <= page <= count or page not in pages:
                problems.append(f'{rid}: visual page must be in source pages')
            if asset.get('file'):
                try:
                    file = contained(job, asset['file'])
                    if not file.is_file():
                        problems.append(f'{rid}: image is missing: {file}')
                except ValueError as e:
                    problems.append(str(e))
            else:
                box = asset.get('bbox', [])
                valid = (isinstance(box, list) and len(box) == 4 and
                         all(type(v) in (int, float) and math.isfinite(v) and 0 <= v <= 1 for v in box))
                if not valid or not (box[0] < box[2] and box[1] < box[3]):
                    problems.append(f'{rid}: bbox must be [left, top, right, bottom] fractions of page size')
                if type(page) is int and not contained(job, f'pages/page-{page:03d}.png').is_file():
                    problems.append(f'{rid}: render source page {page} first')
        if r.get('kind') in ('figure', 'equation') and not r.get('visuals'):
            warnings.append(f'{rid}: no source image attached; verify the text representation')
        if r.get('kind') == 'table':
            table = r.get('table', {})
            headers = table.get('headers', [])
            rows = table.get('rows', [])
            if not headers or not rows or any(len(row) != len(headers) for row in rows):
                problems.append(f'{rid}: table is empty or has inconsistent widths')
            for cell in headers + [c for row in rows for c in row]:
                if not isinstance(cell, dict) or not all(isinstance(cell.get(k), str) and cell[k].strip() for k in ('source', 'target')):
                    problems.append(f'{rid}: each table cell needs source and target text (numbers can be repeated)')
                elif cell.get('alignment') is not None:
                    problems.extend(f'{rid} table cell: {error}' for error in alignment_errors(cell))
        # Numbers and citation tokens are indicators, not proof of translation quality.
        if r.get('kind') == 'paragraph' and r.get('target'):
            for token in set(re.findall(r'\b\d+(?:\.\d+)?(?:%|\b)', r['source'])):
                if token not in r['target']:
                    warnings.append(f'{rid}: review source number {token} against translation')
            for token in set(re.findall(r'\[\d+\]', r['source'])):
                if token not in r['target']:
                    warnings.append(f'{rid}: review citation {token}')
    if len(ids) != len(set(ids)):
        problems.append('Duplicate record IDs')
    expected = manifest.get('expected_ids', [])
    if not expected:
        problems.append('expected_ids inventory has not been recorded')
    elif len(expected) != len(set(expected)) or set(expected) != set(ids):
        problems.append(f'Inventory mismatch; missing={sorted(set(expected)-set(ids))}, unexpected={sorted(set(ids)-set(expected))}')
    current_hash = hashlib.sha256(contained(job, manifest['source_pdf']).read_bytes()).hexdigest()
    if current_hash != manifest.get('source_sha256'):
        problems.append('Source PDF has changed since preparation')
    for name in ('reading_order', 'translation_complete', 'formulas_tables', 'visual_assets'):
        if manifest.get('review', {}).get(name) is not True:
            problems.append(f'Editorial review is incomplete: {name}')
    report = {'structural_errors': problems, 'review_warnings': warnings,
              'counts': dict(Counter(r.get('kind') for r in records)), 'records': len(records),
              'inventory_checked': bool(expected), 'editorial_review': manifest.get('review', {}),
              'semantic_accuracy_automatically_verified': False, 'draft': draft}
    return report


def check(args):
    job, manifest, _ = get_job(args)
    records = load(contained(job, manifest['records_file']))
    report = validate(job, manifest, records)
    save(contained(job, 'audit.json'), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report['structural_errors'] else 0


def image_assets(job, record):
    from PIL import Image
    result = []
    target = contained(job, 'assets')
    target.mkdir(exist_ok=True)
    for index, visual in enumerate(record.get('visuals', []), 1):
        output = contained(target, f'{record["id"]}-{index}.png')
        if visual.get('file'):
            file = contained(job, visual['file'])
            with Image.open(file) as im:
                im.convert('RGB').save(output)
        else:
            file = contained(job, f'pages/page-{visual["page"]:03d}.png')
            with Image.open(file) as im:
                l, t, r, b = visual['bbox']
                box = (math.floor(l*im.width), math.floor(t*im.height), math.ceil(r*im.width), math.ceil(b*im.height))
                im.crop(box).save(output)
        result.append(output)
    return result


def safe_text(text):
    # Escape plain content. Do not turn embedded HTML, scripts, or PDF text into code.
    return '<br>'.join(html.escape(str(text)).split('\n'))


def md_text(text):
    # Keep mathematical text; neutralize HTML without interpolating any source code.
    return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def aligned_text(record, side, key):
    """Wrap reviewed units without changing or duplicating their original text."""
    alignment = record.get('alignment')
    if not alignment:
        if record.get('kind') in ('paragraph', 'figure'):
            return safe_text(record[side])  # Drafts never fall back to paragraph highlighting.
        alignment = {'source': [record['source']], 'target': [record['target']], 'pairs': [[0, 0]]}
    other = 'target' if side == 'source' else 'source'
    column = 0 if side == 'source' else 1
    parts = []
    for index, text in enumerate(alignment[side]):
        peers = ' '.join(f'{key}-{other}-{pair[1-column]}' for pair in alignment['pairs'] if pair[column] == index)
        parts.append(f'<span class="aligned-sentence" data-unit="{key}-{side}-{index}" data-peers="{peers}">{safe_text(text)}</span>')
    return ''.join(parts)


def build(args):
    job, manifest, workspace = get_job(args)
    records = load(contained(job, manifest['records_file']))
    report = validate(job, manifest, records, args.draft)
    save(contained(job, 'audit.json'), report)
    if report['structural_errors'] and not args.draft:
        raise ValueError('Validation failed; see audit.json. Finish review or explicitly use --draft.')
    # Drafts still cannot bypass ID, asset path, page, or schema safety checks.
    fatal = [x for x in report['structural_errors'] if not any(s in x for s in
             ('target text is missing', 'Target title is empty', 'Editorial review is incomplete', 'expected_ids inventory',
              'sentence alignment is missing', 'sentence alignment has not been reviewed'))]
    if fatal:
        raise ValueError('; '.join(fatal))
    source_lang = manifest['languages']['source']
    target_lang = manifest['languages']['target']
    title = manifest['title']['target'] or manifest['title']['source']
    title += ' 论文双语对照'
    if args.draft:
        title += ' 草稿'
    prefix = basename(manifest['output_prefix'] + ('_草稿' if args.draft else ''))
    outputs = [contained(workspace, prefix + suffix) for suffix in ('.html', '.md')]
    if any(p.exists() for p in outputs) and not args.overwrite:
        raise ValueError('Output exists; use a distinct prefix or explicitly pass --overwrite.')
    esc = html.escape
    def pair(record, cls=''):
        source = aligned_text(record, 'source', record['id'])
        target = aligned_text(record, 'target', record['id']) if record.get('target') else '[译文待完成]'
        return f'<div class="columns {cls}"><div class="cell source-text" lang="{esc(source_lang["code"], quote=True)}"><span class="lang">{esc(source_lang["label"])}</span><p>{source}</p></div><div class="cell target-text" lang="{esc(target_lang["code"], quote=True)}"><span class="lang">{esc(target_lang["label"])}</span><p>{target}</p></div></div>'
    def graphic(file, rid):
        blob = base64.b64encode(file.read_bytes()).decode('ascii')
        return f'<img src="data:image/png;base64,{blob}" alt="{esc(rid)} 原文图像" loading="lazy">'
    def table_cell(cell, key):
        return f'<span class="source-text">{aligned_text(cell, "source", key)}</span><span class="target-text">{aligned_text(cell, "target", key)}</span>'
    def md_table(table):
        def cell(c):
            return (md_text(c['source']) + ' / ' + md_text(c['target'])).replace('|', '\\|').replace('\n', ' ')
        rows = ['| ' + ' | '.join(cell(c) for c in table['headers']) + ' |',
                '| ' + ' | '.join('---' for _ in table['headers']) + ' |']
        rows += ['| ' + ' | '.join(cell(c) for c in row) + ' |' for row in table['rows']]
        return '\n'.join(rows)
    parts, toc, md = [], [], [f'# {md_text(title)}\n']
    counts = report['counts']
    intro = f'依据 {manifest["page_count"]} 页原文，按条目提供原文与译文对照，包含 {len(records)} 个条目。公式与插图保留所附原文图像。选中任一侧句子中的文字，另一侧对应句子会高亮；取消选择后高亮消失。'
    md.append(intro + '\n')
    if args.draft:
        md.append('**草稿：尚有未完成译文或未核对内容，不能作为完整翻译交付。**\n')
    for note in manifest.get('editorial_notes', []):
        md.append('译者说明：' + md_text(note) + '\n')
    for record in records:
        kind, rid = record['kind'], record['id']
        source, target = record['source'], record.get('target', '')
        pages = ', '.join(map(str, record['pages']))
        label = f'<div class="source">原文第 {esc(pages)} 页</div>'
        visuals = image_assets(job, record)
        if kind in ('heading', 'title'):
            level = 2 if kind == 'title' else record['level']+1
            markup = f'<div class="columns"><div class="cell source-text"><h{level}>{aligned_text(record, "source", rid)}</h{level}></div><div class="cell target-text"><h{level}>{aligned_text(record, "target", rid)}</h{level}></div></div>'
            parts.append(f'<section class="block heading" id="{rid}">{label}{markup}</section>')
            if kind == 'heading':
                toc.append(f'<a class="{"sub" if level>2 else ""}" href="#{rid}">{esc(target or source)}</a>')
            md.append('#'*level + ' ' + md_text(source) + '\n\n' + md_text(target) + '\n')
        else:
            cls = {'equation':'formula', 'figure':'figure', 'table':'table-block', 'reference':'ref'}.get(kind, 'paragraph')
            body = label
            if kind != 'table':
                body += ''.join(graphic(p, rid) for p in visuals)
            if kind == 'equation':
                if target:
                    body += f'<div class="target-text">{safe_text(target)}</div>'
                body += f'<details><summary>公式文本</summary><pre>{esc(source)}</pre></details>'
            else:
                body += pair(record, 'caption' if kind in ('figure', 'table') else '')
            if kind == 'table':
                table = record['table']
                body += '<div class="table-wrap"><table><thead><tr>' + ''.join('<th>'+table_cell(c, f'{rid}-head-{i}')+'</th>' for i,c in enumerate(table['headers'])) + '</tr></thead><tbody>'
                body += ''.join('<tr>'+''.join('<td>'+table_cell(c, f'{rid}-row-{i}-{j}')+'</td>' for j,c in enumerate(row))+'</tr>' for i,row in enumerate(table['rows'])) + '</tbody></table></div>'
                if visuals:
                    body += '<details><summary>核对原文表格</summary>' + ''.join(graphic(p,rid) for p in visuals) + '</details>'
            for file in visuals:
                rel = file.relative_to(workspace).as_posix()
                md.append(f'![{rid} 原文图像](<{rel}>)\n')
            if kind == 'equation':
                md += ['**公式文本**\n\n' + md_text(source) + '\n', md_text(target) + '\n']
            else:
                md += [f'**{source_lang["label"]}（原文第 {pages} 页）**\n\n{md_text(source)}\n',
                       f'**{target_lang["label"]}**\n\n{md_text(target or "[译文待完成]")}\n']
            if kind == 'table':
                md.append(md_table(record['table']) + '\n')
            if record.get('translator_note'):
                body += '<p class="notes">译者说明：' + safe_text(record['translator_note']) + '</p>'
                md.append('译者说明：' + md_text(record['translator_note']) + '\n')
            parts.append(f'<section class="block graphic {cls}" id="{rid}">{body}</section>')
    glossary = manifest.get('glossary', [])
    if glossary:
        table = {'headers':[{'source':'Term','target':'术语'}, {'source':'Translation','target':'译法'}],
                 'rows':[[{'source':c['source'],'target':c['source']}, {'source':c['target'],'target':c['target']}] for c in glossary]}
        gl = '<section class="block" id="translator-glossary"><h2>译者附录 术语对照</h2><p class="notes">辅助阅读内容，不属于论文正文。</p><div class="table-wrap"><table><thead><tr><th>原文</th><th>译法</th></tr></thead><tbody>'
        gl += ''.join(f'<tr><td>{aligned_text(c, "source", f"glossary-{i}")}</td><td>{aligned_text(c, "target", f"glossary-{i}")}</td></tr>' for i,c in enumerate(glossary)) + '</tbody></table></div></section>'
        parts.append(gl)
        toc.append('<a href="#translator-glossary">译者附录 术语对照</a>')
        md += ['## 译者附录 术语对照\n', '辅助阅读内容，不属于论文正文。\n',
               '| 原文 | 译法 |\n| --- | --- |\n' + '\n'.join('| '+md_text(c['source']).replace('|','\\|')+' | '+md_text(c['target']).replace('|','\\|')+' |' for c in glossary) + '\n']
    css = (SKILL/'assets'/'reader.css').read_text(encoding='utf-8')
    js = (SKILL/'assets'/'reader.js').read_text(encoding='utf-8')
    notes = ''.join('<p class="intro">译者说明：'+safe_text(n)+'</p>' for n in manifest.get('editorial_notes', []))
    banner = '<p class="draft-banner">草稿：尚有未完成译文或未核对内容。</p>' if args.draft else ''
    document = f'<!doctype html><html lang="{esc(target_lang["code"],quote=True)}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title><style>{css}</style></head><body><header><h1>{esc(title)}</h1><p class="intro">{esc(intro)}</p>{notes}{banner}</header><div class="bar"><button data-mode="both" class="active">双语对照</button><button data-mode="target">仅{esc(target_lang["label"])}</button><button data-mode="source">仅{esc(source_lang["label"])}</button><input id="search" aria-label="搜索" placeholder="搜索术语、章节或数值"><span id="count"></span></div><div class="layout"><nav aria-label="目录">{"".join(toc)}</nav><article>{"".join(parts)}</article></div><script>{js}</script></body></html>'
    outputs[0].write_text(document, encoding='utf-8')
    outputs[1].write_text('\n'.join(md), encoding='utf-8')
    save(contained(job, 'build.json'), {'outputs':[str(p) for p in outputs], 'draft':args.draft,
                                      'records':len(records), 'counts':counts,
                                      'source_sha256':manifest['source_sha256']})
    print(json.dumps({'outputs':[str(p) for p in outputs], 'review_warnings':report['review_warnings']}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('init', help='Copy PDF and extract source text/links to a new workspace job')
    p.add_argument('--workspace', required=True)
    p.add_argument('--pdf', required=True)
    p.add_argument('--name', required=True)
    p.add_argument('--render', action='store_true')
    p.add_argument('--poppler-bin')
    p.add_argument('--dpi', type=int, default=160)
    p.set_defaults(func=init)
    p = commands.add_parser('render', help='Render source pages for visual inspection and normalized crops')
    p.add_argument('--job', required=True)
    p.add_argument('--poppler-bin')
    p.add_argument('--dpi', type=int, default=160)
    p.set_defaults(func=render)
    p = commands.add_parser('check', help='Check structure and editorial review flags; not semantic accuracy')
    p.add_argument('--job', required=True)
    p.set_defaults(func=check)
    p = commands.add_parser('build', help='Publish self-contained HTML and Markdown in workspace root')
    p.add_argument('--job', required=True)
    p.add_argument('--draft', action='store_true')
    p.add_argument('--overwrite', action='store_true')
    p.set_defaults(func=build)
    args = parser.parse_args()
    try:
        return args.func(args) or 0
    except (ValueError, KeyError, TypeError, OSError, subprocess.CalledProcessError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())
