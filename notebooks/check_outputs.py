import json, os, sys

nb_dir = os.path.dirname(os.path.abspath(__file__))
notebooks = ['02-custom-evaluator-register.ipynb', '03-red-team-taxonomy.ipynb', '04-red-team-run.ipynb']

for nb_name in notebooks:
    path = os.path.join(nb_dir, nb_name)
    if not os.path.exists(path):
        print(f'\n=== {nb_name}: FILE NOT FOUND ===')
        continue
    nb = json.loads(open(path).read())
    print(f'\n======== {nb_name} ========')
    has_output = False
    for i, cell in enumerate(nb['cells']):
        if cell['cell_type'] == 'code' and cell.get('outputs'):
            has_output = True
            print(f'--- Cell {i+1} ---')
            for out in cell['outputs']:
                if 'text' in out:
                    print(''.join(out['text']))
                elif 'traceback' in out:
                    print('ERROR:', '\n'.join(out['traceback'][:3]))
                elif 'data' in out:
                    for k,v in out['data'].items():
                        if isinstance(v, list):
                            print(''.join(v))
                        else:
                            print(str(v))
    if not has_output:
        print('No cell outputs found.')
