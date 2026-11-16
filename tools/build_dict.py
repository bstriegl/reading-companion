"""Baut die Wörterbuch-Dateien des Reading Companion aus WikDict en-de (CC BY-SA 3.0, Wiktionary-Daten).
Aufruf: python3 build_dict.py <en-de.sqlite3> <zielordner>"""
import sqlite3, json, re, sys, os, collections, gzip
from wordfreq import top_n_list, zipf_frequency
import lemminflect

src, out = sys.argv[1], sys.argv[2]
POS = {'Noun':'n','Verb':'v','Adjective':'adj','Adverb':'adv','Proper_noun':'name','Phrase':'phr','Prepositional_phrase':'phr',
       'Interjection':'interj','Preposition':'prep','Proverb':'saying','Numeral':'num','Number':'num','Pronoun':'pron',
       'Conjunction':'conj','Determiner':'det','Particle':'part','Article':'art','Postposition':'prep','Contraction':'short'}
SKIP_POS = {'Prefix','Suffix','Infix','Symbol','Letter','Circumfix','Interfix','Affix','Punctuation_mark','Diacritical_mark'}
BLOCK = re.compile(r'\b(vulgar|sex|sexual|sexually|intercourse|penis|vagina|genital|genitals|anus|anal|orgasm|ejaculat\w*|masturbat\w*|prostitut\w*|slur|offensive|derogatory|pejorative|faeces|feces|excrement|defecat\w*|urinat\w*|testicle\w*|breasts?|buttocks|semen|erection|fellatio|coitus|copulat\w*|homosexual\w*)\b', re.I)
MAX_SENSES, MAX_GLOSS = 8, 90

rows = sqlite3.connect(src).execute(
    "select lexentry,sense,written_rep,trans_list,score,is_good,importance from translation").fetchall()
heads = collections.defaultdict(list)          # Stichwort -> [(gut, wichtigkeit, score, pos, gloss, trans)]
for lex, sense, w, trans, score, good, imp in rows:
    if not w or not trans or w.startswith('#') or len(w) > 40: continue
    m = re.search(r'__(\w+?)__', lex or '')
    p = m.group(1) if m else ''
    if p in SKIP_POS or w.startswith('-') or w.endswith('-'): continue
    if len(w.split()) > 6: continue
    gloss = (sense or '').strip()
    if BLOCK.search(gloss): continue
    tl = [t.strip() for t in trans.split('|') if t.strip()][:5]
    if not tl: continue
    if len(gloss) > MAX_GLOSS: gloss = gloss[:MAX_GLOSS].rsplit(' ', 1)[0] + ' …'
    heads[w].append((good or 0, imp or 0, score or 0, POS.get(p, ''), gloss, '|'.join(tl)))

entries = {}
for w, ss in heads.items():
    good = [s for s in ss if s[0]]
    use = good if good else sorted(ss, key=lambda s: -s[2])[:3]
    use.sort(key=lambda s: (-s[2], -s[1], not s[4]))   # verbreitete Übersetzungen zuerst, dann Wichtigkeit
    seen, covered, res = set(), collections.defaultdict(set), []
    for g, imp, sc, p, gloss, tr in use:
        k = (p, tr)
        if k in seen: continue
        words = list(dict.fromkeys(tr.split('|')))
        if not gloss and set(words) <= covered[p]: continue      # ohne Erklärung und nichts Neues
        seen.add(k); covered[p].update(words); res.append([p, gloss, '|'.join(words)])
        if len(res) >= MAX_SENSES: break
    entries[w] = {'s': res, 'good': bool(good)}

lower = collections.defaultdict(list)          # kleingeschrieben -> Stichwörter
for w in entries: lower[w.lower()].append(w)
has_good = lambda k: any(entries[w]['good'] for w in lower.get(k, []))
exact_good = lambda k: k in entries and entries[k]['good']

# ---- Formen: flektierte Form / britische Schreibung -> Grundform(en)
BR = [(r'isation', 'ization'), (r'isations', 'izations'), (r'ise$', 'ize'), (r'ises$', 'izes'), (r'ised$', 'ized'), (r'ising$', 'izing'),
      (r'yse$', 'yze'), (r'ysed$', 'yzed'), (r'ysing$', 'yzing'), (r'our', 'or'), (r'tre$', 'ter'), (r'tres$', 'ters'), (r'bre$', 'ber'),
      (r'ence$', 'ense'), (r'ogue$', 'og'), (r'ogues$', 'ogs'), (r'lled$', 'led'), (r'lling$', 'ling'), (r'ller$', 'ler'), (r'llers$', 'lers'),
      (r'ae', 'e'), (r'oe', 'e'), (r'mme$', 'm'), (r'mmes$', 'ms'), (r'grey', 'gray'), (r'plough', 'plow'), (r'tyre', 'tire'),
      (r'kerb', 'curb'), (r'cheque', 'check'), (r'aluminium', 'aluminum'), (r'jewellery', 'jewelry'), (r'sceptic', 'skeptic'),
      (r'mould', 'mold'), (r'storey', 'story'), (r'pyjamas', 'pajamas'), (r'moustache', 'mustache'), (r'cosy', 'cozy'), (r'draught', 'draft')]
def american(t):
    res = []
    for a, b in BR:
        u = re.sub(a, b, t, count=1)
        if u != t: res.append(u)
    return res
EXTRA = {"n't": ['not'], "won't": ['will'], "can't": ['can'], "shan't": ['shall'], "'ve": ['have'], "'ll": ['will'], "'re": ['be'], "'m": ['be'],
         'an': ['a'], 'worse': ['bad'], 'worst': ['bad'], 'best': ['good', 'well'], 'further': ['far'], 'furthest': ['far'], 'elder': ['old'],
         'eldest': ['old'], 'less': ['little'], 'least': ['little'], 'more': ['much', 'many'], 'most': ['much', 'many']}
forms = collections.defaultdict(list)
def add(form, lemma):
    if lemma != form and lemma not in forms[form] and has_good(lemma): forms[form].append(lemma)
vocab = [t for t in top_n_list('en', 220000) if re.fullmatch(r"[a-z][a-z'\-]*", t)]
for t in vocab:
    for upos, lems in lemminflect.getAllLemmas(t).items():
        for l in lems: add(t, l.lower())
    for u in american(t):
        if has_good(u) and not exact_good(t): add(t, u)
        elif not exact_good(t):
            for upos, lems in lemminflect.getAllLemmas(u).items():
                for l in lems: add(t, l.lower())
for k, v in EXTRA.items():
    for l in v: add(k, l)
forms = {k: v[:3] for k, v in forms.items() if v}

# ---- Ausgabe: je Anfangsbuchstabe eine Datei
shard = lambda k: k[0] if 'a' <= k[0] <= 'z' else '_'
files = collections.defaultdict(lambda: {'w': {}, 'f': {}})
for k, ws in lower.items():
    lst = []
    for w in sorted(ws, key=lambda w: (not entries[w]['good'], w != k)):
        for s in entries[w]['s']: lst.append(s if w == k else s + [w])
    files[shard(k)]['w'][k] = lst[:12]
for k, v in forms.items(): files[shard(k)]['f'][k] = v
os.makedirs(out, exist_ok=True)
tot = totz = 0
for s, d in sorted(files.items()):
    b = json.dumps(d, ensure_ascii=False, separators=(',', ':')).encode()
    open(os.path.join(out, s + '.json'), 'wb').write(b)
    tot += len(b); totz += len(gzip.compress(b))
print(len(lower), 'Stichwörter,', len(forms), 'Formen,', len(files), 'Dateien,', round(tot/1e6, 2), 'MB,', round(totz/1e6, 2), 'MB gzip')
print({s: round(len(gzip.compress(open(os.path.join(out, s + '.json'), 'rb').read()))/1e3) for s in sorted(files)})
