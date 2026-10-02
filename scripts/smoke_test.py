"""Exercise generic publishing and failure guards with a generated two-page PDF."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--poppler-bin', required=True)
    args = parser.parse_args()
    workspace = Path(args.workspace).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    temp = workspace / 'tmp'
    temp.mkdir(exist_ok=True)
    for key in ('TMP', 'TEMP', 'TMPDIR'):
        os.environ[key] = str(temp)
    from reportlab.pdfgen import canvas
    source = workspace / 'synthetic-source.pdf'
    if source.exists():
        raise ValueError('Use a fresh test workspace; do not overwrite previous tests.')
    c = canvas.Canvas(str(source), pagesize=(600, 800))
    c.setFont('Helvetica', 14)
    c.drawString(40, 740, 'A Small Synthetic Study')
    c.setFont('Helvetica', 11)
    c.drawString(40, 700, 'Abstract')
    c.drawString(40, 670, 'The measured delay is 3.2 ms [A].')
    c.drawString(40, 650, 'The receiver stays synchronized.')
    c.drawString(40, 630, 'A second mode shares the hardware.')
    c.drawString(40, 520, 'x = a + b     (1)')
    c.rect(40, 250, 180, 70)
    c.drawString(50, 278, 'Input -> Output')
    c.showPage()
    c.setPageSize((800, 600))
    c.setFont('Helvetica', 11)
    c.drawString(40, 530, 'Parameter     Value')
    c.drawString(40, 500, 'Delay              3.2 ms')
    c.drawString(40, 400, '[A] J. Doe, A model, Example Journal, 2024.')
    c.drawString(430, 400, '[B] A. Roe, A method, Example Journal, 2025.')
    c.linkURL('https://example.org/study', (40, 380, 200, 395), relative=0)
    c.save()
    tool = Path(__file__).with_name('paper_translate.py')
    calls = []
    def run(command, expected=0):
        proc = subprocess.run([sys.executable, '-X', 'utf8', '-B', str(tool)] + command,
                              cwd=workspace, capture_output=True, text=True, encoding='utf-8')
        calls.append({'command':command[0], 'expected':expected, 'actual':proc.returncode})
        if proc.returncode != expected:
            raise AssertionError(f'{command}: {proc.stdout}\n{proc.stderr}')
        return proc
    run(['init', '--workspace', str(workspace), '--pdf', str(source), '--name', 'generic-example',
         '--render', '--poppler-bin', args.poppler_bin, '--dpi', '100'])
    job = workspace / 'analysis/paper-translations/generic-example'
    manifest_path, records_path = job/'paper.json', job/'records.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    assert manifest['page_count'] == 2
    pages = json.loads((job/'source_pages.json').read_text(encoding='utf-8'))
    assert pages[0]['width_pt'] != pages[1]['width_pt']
    assert pages[1]['links'][0]['uri'] == 'https://example.org/study'
    def write_records(value):
        records_path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    def write_manifest():
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    records = [
        {'id':'title-one','kind':'title','pages':[1],'source':'A Small Synthetic Study','target':'一项小型合成研究'},
        {'id':'abstract-one','kind':'heading','level':1,'pages':[1],'source':'Abstract','target':'摘要'},
        {'id':'paragraph-one','kind':'paragraph','pages':[1],
         'source':'The measured delay is 3.2 ms [A]. The receiver stays synchronized. A second mode shares the hardware.',
         'target':'接收端保持同步。测得的时延为 3.2 ms [A]。第二种模式共享硬件。',
         'alignment':{'source':['The measured delay is 3.2 ms [A]. ','The receiver stays synchronized. ','A second mode shares the hardware.'],
                      'target':['接收端保持同步。','测得的时延为 3.2 ms [A]。','第二种模式共享硬件。'],
                      'pairs':[[0,1],[1,0],[2,2]],'reviewed':True}},
        {'id':'equation-one','kind':'equation','pages':[1],'source':'x = a + b  (1)','target':'','visuals':[{'page':1,'bbox':[0.06,0.325,0.47,0.365]}]},
        {'id':'figure-one','kind':'figure','pages':[1],'source':'Fig. 1. Input and output.','target':'图 1. 输入与输出。','visuals':[{'page':1,'bbox':[0.055,0.585,0.38,0.695]}]},
        {'id':'settings-table','kind':'table','pages':[2],'source':'Table I. Settings.','target':'表 I. 设置。',
         'table':{'headers':[{'source':'Parameter','target':'参数'},{'source':'Value','target':'数值'}],
                  'rows':[[{'source':'Delay','target':'时延'},{'source':'3.2 ms','target':'3.2 ms'}]]},
         'visuals':[{'page':2,'bbox':[0.045,0.095,0.32,0.185]}]},
        {'id':'reference-a','kind':'reference','pages':[2],'source':'[A] J. Doe, A model, Example Journal, 2024.','target':'[A] J. Doe，《一种模型》，Example Journal，2024 年。'},
        {'id':'reference-b','kind':'reference','pages':[2],'source':'[B] A. Roe, A method, Example Journal, 2025.','target':'[B] A. Roe，《一种方法》，Example Journal，2025 年。'},
    ]
    records[4]['alignment']={'source':[records[4]['source']], 'target':[records[4]['target']], 'pairs':[[0,0]], 'reviewed':True}
    records.append({'id':'split-sentence','kind':'paragraph','pages':[2],
                    'source':'The pool serves two modes and both remain active.',
                    'target':'共享池服务两种模式。两者均保持活动。',
                    'alignment':{'source':['The pool serves two modes and both remain active.'],
                                 'target':['共享池服务两种模式。','两者均保持活动。'],
                                 'pairs':[[0,0],[0,1]],'reviewed':True}})
    manifest['title']['target']='合成示例'
    manifest['expected_ids']=[x['id'] for x in records]
    manifest['glossary']=[{'source':'delay','target':'时延'}]
    manifest['output_prefix']='通用技能测试_对照'
    write_records(records);write_manifest()
    run(['build','--job',str(job)],2)  # Unreviewed content is not a final translation.
    run(['build','--job',str(job),'--draft'])
    draft = workspace/'通用技能测试_对照_草稿.html'
    assert draft.is_file() and '草稿' in draft.read_text(encoding='utf-8')
    manifest['review']={k:True for k in manifest['review']};write_manifest()
    run(['check','--job',str(job)])
    run(['build','--job',str(job)])
    final = workspace/'通用技能测试_对照.html'
    text = final.read_text(encoding='utf-8')
    assert text.count('data:image/png;base64,')==3
    assert '3.2 ms' in text and '[A]' in text and '[B]' in text
    assert 'OpenSat' not in text
    run(['build','--job',str(job)],2)  # No silent output overwrite.
    run(['build','--job',str(job),'--overwrite'])
    bad = json.loads(json.dumps(records));bad[2].pop('alignment');write_records(bad)
    run(['check','--job',str(job)],1)
    run(['build','--job',str(job),'--draft','--overwrite'])
    assert 'paragraph-one-source-0' not in draft.read_text(encoding='utf-8')
    bad = json.loads(json.dumps(records));bad[2]['alignment']['source'].reverse();write_records(bad)
    run(['check','--job',str(job)],1)
    bad = json.loads(json.dumps(records));bad[2]['alignment']['pairs']=[[0,0]];write_records(bad)
    run(['check','--job',str(job)],1)
    bad = json.loads(json.dumps(records));bad[2]['alignment']['pairs'][0][1]=99;write_records(bad)
    run(['check','--job',str(job)],1)
    bad = json.loads(json.dumps(records));bad[2]['alignment']['reviewed']=False;write_records(bad)
    run(['build','--job',str(job),'--overwrite'],2)
    bad = json.loads(json.dumps(records));bad[2]['target']='';write_records(bad)
    run(['build','--job',str(job),'--overwrite'],2)
    bad = json.loads(json.dumps(records));bad[1]['id']=bad[0]['id'];write_records(bad)
    run(['check','--job',str(job)],1)
    bad = json.loads(json.dumps(records));bad[3]['visuals'][0]['bbox']=[-0.1,0,1,1];write_records(bad)
    run(['build','--job',str(job),'--draft','--overwrite'],2)
    bad = json.loads(json.dumps(records));bad[3]['visuals'][0]={'page':1,'file':'../../../../outside.png'};write_records(bad)
    run(['build','--job',str(job),'--draft','--overwrite'],2)
    write_records(records)
    manifest['output_prefix']='../outside';write_manifest()
    run(['build','--job',str(job),'--overwrite'],2)
    manifest['output_prefix']='通用技能测试_对照';write_manifest()
    manifest['expected_ids'].append('missing-source-item');write_manifest()
    run(['check','--job',str(job)],1)
    manifest['expected_ids'].pop();write_manifest()
    # Treat all input as text; do not emit source HTML or scripts.
    bad = json.loads(json.dumps(records));bad[2]['source']='<script>alert(1)</script>'
    bad[2]['target']='字符串';bad[2]['alignment']={'source':[bad[2]['source']], 'target':[bad[2]['target']], 'pairs':[[0,0]], 'reviewed':True};write_records(bad)
    run(['build','--job',str(job),'--overwrite'])
    assert '<script>alert(1)</script>' not in final.read_text(encoding='utf-8')
    write_records(records)
    run(['build','--job',str(job),'--overwrite'])
    run(['check','--job',str(job)])
    report={'passed':True,'source_pages':2,'page_sizes_differ':True,'references':2,
            'bibliography_uses_letters':True,'calls':calls,'final_html':str(final)}
    (workspace/'smoke_test_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':
    if hasattr(sys.stdout,'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    main()
