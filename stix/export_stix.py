"""Export of the Akira population of MOMTC v2.0 to a STIX 2.1 bundle.
Input : MOMTC v2.0 (RDF/XML conversion of MOMTC_v2_0.ofn, 804 axioms).
Output: momtc_akira_stix21.json + export_report.json
Only STIX 2.1 core objects, properties, vocabularies and relationship types are used (no custom content).
Identifiers are deterministic (UUID with version-4 layout derived from the SHA-256 of the MOMTC IRI),
so that the export is reproducible byte for byte."""
import rdflib, json, uuid, hashlib, re, collections, sys, pathlib
HERE=pathlib.Path(__file__).resolve().parent
from rdflib import RDF, URIRef, Literal
SRC=sys.argv[1] if len(sys.argv)>1 else str(HERE.parent/'serialisations'/'MOMTC.rdf')
A='https://attack.mitre.org/'
g=rdflib.Graph(); g.parse(SRC,format='xml')
TS='2026-11-05T00:00:00.000Z'          # export timestamp (created/modified)
VALID_FROM='2024-04-18T00:00:00Z'      # publication date of advisory AA24-109A, source of the indicators
def loc(u): return str(u).replace(A,'').replace('MITRE_ATT&CK:','')
def cls(name):
    if name in ('Offensive_Techniques','Sub-Technique','Tactics'): return URIRef(A+'MITRE_ATT&CK:'+name)
    return URIRef(A+name)
def inst(c): return sorted({s for s in g.subjects(RDF.type,cls(c)) if isinstance(s,URIRef)},key=str)
def val(s,p):
    v=list(g.objects(s,URIRef(A+p))); return v[0] if v else None
def objs(p): return sorted(((s,o) for s,o in g.subject_objects(URIRef(A+p))),key=lambda x:(str(x[0]),str(x[1])))
def sid(t,iri):
    b=bytearray(hashlib.sha256(str(iri).encode()).digest()[:16]); b[6]=(b[6]&0x0F)|0x40; b[8]=(b[8]&0x3F)|0x80
    return f'{t}--{uuid.UUID(bytes=bytes(b))}'
def pretty(l):
    l=re.sub(r'^(TA\d{4}|T\d{4}(_\d{3})?|D3_[A-Z]+|CVE_\d+_\d+|IoC|HF|IT|DM|RA)_?','',l)
    return l.replace('_',' ').strip()
def ts(v):
    s=str(v); return s+'Z' if not s.endswith('Z') else s
objects={}; ids={}; skipped=collections.Counter(); notes=[]; normalised=[]
base=lambda t,iri:{'type':t,'spec_version':'2.1','id':sid(t,iri),'created':TS,'modified':TS}
# ---------- threat actors
for s in inst('Threat_Actor_Profiling'):
    o=base('threat-actor',s); o['name']=loc(s).replace('_',' ')
    for p,k in (('first_observed','first_seen'),('last_observed','last_seen')):
        v=val(s,p)
        if v is not None: o[k]=ts(v)
    lev=val(s,'has_sophistication_level')
    if lev is not None:
        name=loc(lev).lower()
        if name in {'none','minimal','intermediate','advanced','expert','innovator','strategic'}: o['sophistication']=name
    objects[s]=o
# ---------- campaigns
for s in inst('Threat_Campaign'):
    o=base('campaign',s); o['name']=loc(s).replace('_',' '); objects[s]=o
# ---------- capabilities: malware vs tool (modelling decision documented in the appendix, after AA24-109A)
MALWARE={'Akira_Encryptor','Megazord'}; TOOL_TYPES={'AnyDesk':['remote-access']}
for s in inst('Threat_Capability'):
    l=loc(s)
    if l in MALWARE:
        o=base('malware',s); o['name']=l.replace('_',' '); o['is_family']=True; o['malware_types']=['ransomware']
    else:
        o=base('tool',s); o['name']=l
        if l in TOOL_TYPES: o['tool_types']=TOOL_TYPES[l]
    objects[s]=o
# ---------- infrastructure
for s in inst('Infrastructure'):
    o=base('infrastructure',s); o['name']=loc(s).replace('_',' ')
    if 'C2' in loc(s): o['infrastructure_types']=['command-and-control']
    objects[s]=o
# ---------- attack patterns (techniques and sub-techniques)
tactic_phase={}
for t in inst('Tactics'):
    m=re.match(r'(TA\d{4})_(.*)',loc(t)); tactic_phase[t]=m.group(2).lower().replace('_','-')
for c in ('Offensive_Techniques','Sub-Technique'):
    for s in inst(c):
        if s in objects: continue
        l=loc(s); m=re.match(r'(T\d{4})(?:_(\d{3}))?_',l)
        tid=str(val(s,'has_technique_id') or val(s,'has_sub_technique_id') or (m.group(1)+('.'+m.group(2) if m.group(2) else '')))
        o=base('attack-pattern',s); o['name']=pretty(l)
        refs=[{'source_name':'mitre-attack','external_id':tid}]
        for cp in g.objects(s,URIRef(A+'realizes_attack_pattern')):
            cid=str(val(cp,'has_capec_identifier'))
            refs.append({'source_name':'capec','external_id':cid})
        for w in g.objects(s,URIRef(A+'exploits_weakness')):
            refs.append({'source_name':'cwe','external_id':str(val(w,'has_cwe_identifier'))})
        o['external_references']=refs
        ph=[{'kill_chain_name':'mitre-attack','phase_name':tactic_phase[t]} for t in g.objects(s,URIRef(A+'belongs_to_tactic'))]
        if ph: o['kill_chain_phases']=ph
        objects[s]=o
# ---------- vulnerabilities
for s in inst('CVE_Vulnerabilities'):
    cve=str(val(s,'has_cve_identifier')); o=base('vulnerability',s); o['name']=cve
    refs=[{'source_name':'cve','external_id':cve}]
    for w in sorted(g.objects(s,URIRef(A+'exhibits_weakness')),key=str):
        refs.append({'source_name':'cwe','external_id':str(val(w,'has_cwe_identifier'))})
    o['external_references']=refs; objects[s]=o
# ---------- courses of action (D3FEND countermeasures and sub-countermeasures)
for c in ('D3FEND_Countermeasure','D3FEND_Sub_Countermeasure'):
    for s in inst(c):
        if s in objects: continue
        l=loc(s); m=re.match(r'D3_([A-Z]+)_(.*)',l)
        if not m: skipped['course-of-action without D3FEND identifier: '+l]+=1; continue
        o=base('course-of-action',s); o['name']=m.group(2).replace('_',' ')
        refs=[{'source_name':'d3fend','external_id':'D3-'+m.group(1)}]
        for ctl in g.objects(s,URIRef(A+'is_formalized_by')):
            mm=re.match(r'NIST_([A-Z]{2})_(\d+)_',loc(ctl))
            refs.append({'source_name':'NIST SP 800-53 Rev. 5','external_id':mm.group(1)+'-'+mm.group(2)})
        o['external_references']=refs; objects[s]=o
# ---------- indicators
for s in inst('Indicators_Of_Compromise'):
    pat=val(s,'has_indicator_pattern')
    if pat is None: skipped['indicator without pattern']+=1; continue
    o=base('indicator',s); o['name']=pretty(loc(s))
    o['description']='Indicator of compromise of the Akira ransomware reported in joint advisory AA24-109A.'
    p=str(pat); fixed=re.sub(r'"([^"]*)"',r"'\1'",p)
    if fixed!=p: normalised.append({'individual':loc(s),'original':p,'exported':fixed})
    o['pattern']=fixed; o['pattern_type']='stix'; o['valid_from']=VALID_FROM
    conf=val(s,'has_confidence')
    if conf is not None: o['confidence']=int(round(float(conf)*100))
    objects[s]=o
# ---------- relationships: (MOMTC property, reverse?, STIX relationship type)
REL=[('orchestrates',True,'attributed-to'),('campaign_employs',False,'uses'),('employs_capability',False,'uses'),
     ('controls_infrastructure',False,'uses'),('is_implemented_via',True,'uses'),('is_attributable_to',False,'indicates'),
     ('generates_indicator',True,'indicates'),('mitigates',False,'mitigates'),('is_remediated_by',True,'remediates'),
     ('is_behaviorally_similar_to',False,'related-to'),('is_part_of_technique',False,'related-to'),('has_sub_countermeasure',False,'related-to')]
rels=[]; seen=set(); relcount=collections.Counter()
for p,rev,rt in REL:
    for s,o in objs(p):
        a,b=(o,s) if rev else (s,o)
        if a not in objects or b not in objects:
            skipped[f'{p}: endpoint without STIX object']+=1; continue
        if rt=='indicates' and objects[b]['type']=='vulnerability':
            skipped[f'{p}: indicator -> vulnerability is not a suggested STIX 2.1 relationship']+=1; continue
        key=(objects[a]['id'],rt,objects[b]['id'])
        if key in seen or (rt=='related-to' and (objects[b]['id'],rt,objects[a]['id']) in seen): continue
        seen.add(key)
        r={'type':'relationship','spec_version':'2.1','id':sid('relationship',f'{s}|{p}|{o}'),'created':TS,'modified':TS,
           'relationship_type':rt,'source_ref':objects[a]['id'],'target_ref':objects[b]['id'],
           'description':f'Exported from MOMTC property {p}'}
        rels.append(r); relcount[(p,rt)]+=1
bundle={'type':'bundle','id':sid('bundle','MOMTC-v2.0-Akira'),'objects':sorted(objects.values(),key=lambda x:(x['type'],x['name']))+sorted(rels,key=lambda r:r['id'])}
json.dump(bundle,open(HERE/'momtc_akira_stix21.json','w'),indent=2,ensure_ascii=False)
# ---------- report
all_ind={s for s in g.subjects(RDF.type,None) if isinstance(s,URIRef) and (s,RDF.type,URIRef('http://www.w3.org/2002/07/owl#NamedIndividual')) in g}
rep={'source':(str(pathlib.Path(SRC).resolve().relative_to(HERE.parent)) if pathlib.Path(SRC).resolve().is_relative_to(HERE.parent) else pathlib.Path(SRC).name),'individuals_in_ontology':len(all_ind),'sdo_exported':len(objects),
     'sdo_by_type':dict(collections.Counter(o['type'] for o in objects.values())),
     'relationships_exported':len(rels),'relationships_by_property':{f'{p} -> {rt}':n for (p,rt),n in relcount.items()},
     'not_exported':dict(skipped),'patterns_normalised':normalised}
json.dump(rep,open(HERE/'export_report.json','w'),indent=1)
print(json.dumps(rep,indent=1))
