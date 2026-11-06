import json, sys, stix2, pathlib, importlib.metadata as m
HERE=pathlib.Path(__file__).resolve().parent
from stix2validator import validate_file, ValidationOptions
f=sys.argv[1] if len(sys.argv)>1 else str(HERE/'momtc_akira_stix21.json')
out={'validator':'stix2-validator '+m.version('stix2-validator'),'library':'stix2 '+m.version('stix2'),'schemas':'oasis-open/cti-stix2-json-schemas 9af1db4'}
for strict in (False,True):
    res=validate_file(f, ValidationOptions(version='2.1', strict=strict))
    errs=[(o.object_id,str(e)) for o in (res.object_results or []) for e in (o.errors or [])]
    warns=[(o.object_id,str(w)) for o in (res.object_results or []) for w in (o.warnings or [])]
    out['strict' if strict else 'default']={'valid':res.is_valid,'errors':len(errs),'warnings':len(warns),'details':errs+warns}
    print('strict' if strict else 'default','valid=',res.is_valid,'errors=',len(errs),'warnings=',len(warns))
    for x in errs: print('  ERR',x)
    for x in warns: print('  WARN',x)
b=stix2.parse(open(f).read(), allow_custom=False)
out['stix2_parse']='ok, %d objects, no custom content'%len(b.objects); print(out['stix2_parse'])
json.dump(out,open(HERE/'validation_report.json','w'),indent=1)
