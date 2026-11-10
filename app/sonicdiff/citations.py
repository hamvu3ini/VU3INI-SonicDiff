"""References for the methods appendix in IEEE, ACS, AIP, APA 7th and MLA 9th style, plus BibTeX.

Entries cover the methods and software SonicDiff uses. Check each against the
original before thesis submission.
"""
from . import VERSION

REFS = [
    dict(key="boersma_praat", type="software", authors=[("Paul", "Boersma"), ("David", "Weenink")],
         title="Praat: Doing phonetics by computer", year="2024", version="6.4", publisher="University of Amsterdam",
         url="https://www.praat.org"),
    dict(key="jadoul2018parselmouth", type="article", authors=[("Yannick", "Jadoul"), ("Bill", "Thompson"), ("Bart", "de Boer")],
         title="Introducing Parselmouth: A Python interface to Praat", journal="Journal of Phonetics", volume="71",
         pages="1–15", year="2018", doi="10.1016/j.wocn.2018.07.001"),
    dict(key="mcfee2015librosa", type="inproceedings",
         authors=[("Brian", "McFee"), ("Colin", "Raffel"), ("Dawen", "Liang"), ("Daniel P. W.", "Ellis"), ("Matt", "McVicar"),
                  ("Eric", "Battenberg"), ("Oriol", "Nieto")],
         title="librosa: Audio and music signal analysis in Python",
         booktitle="Proceedings of the 14th Python in Science Conference", pages="18–25", year="2015"),
    dict(key="seabold2010statsmodels", type="inproceedings", authors=[("Skipper", "Seabold"), ("Josef", "Perktold")],
         title="Statsmodels: Econometric and statistical modeling with Python",
         booktitle="Proceedings of the 9th Python in Science Conference", year="2010"),
    dict(key="gulati2014tonic", type="article",
         authors=[("Sankalp", "Gulati"), ("Ashwin", "Bellur"), ("Justin", "Salamon"), ("H. G.", "Ranjani"), ("Vignesh", "Ishwar"),
                  ("Hema A.", "Murthy"), ("Xavier", "Serra")],
         title="Automatic tonic identification in Indian art music: Approaches and evaluation",
         journal="Journal of New Music Research", volume="43", number="1", pages="53–71", year="2014"),
    dict(key="srinivasamurthy2021saraga", type="article",
         authors=[("Ajay", "Srinivasamurthy"), ("Sankalp", "Gulati"), ("Rafael", "Caro Repetto"), ("Xavier", "Serra")],
         title="Saraga: Open datasets for research on Indian art music", journal="Empirical Musicology Review",
         volume="16", number="1", year="2021"),
    dict(key="wilkins2018vocalset", type="inproceedings",
         authors=[("Julia", "Wilkins"), ("Prem", "Seetharaman"), ("Alison", "Wahl"), ("Bryan", "Pardo")],
         title="VocalSet: A singing voice dataset",
         booktitle="Proceedings of the 19th International Society for Music Information Retrieval Conference", year="2018"),
    dict(key="hillenbrand1994cpp", type="article",
         authors=[("James", "Hillenbrand"), ("Ronald A.", "Cleveland"), ("Robert L.", "Erickson")],
         title="Acoustic correlates of breathy vocal quality", journal="Journal of Speech and Hearing Research",
         volume="37", number="4", pages="769–778", year="1994"),
    dict(key="sundberg1974singing", type="article", authors=[("Johan", "Sundberg")],
         title="Articulatory interpretation of the “singing formant”",
         journal="The Journal of the Acoustical Society of America", volume="55", number="4", pages="838–844", year="1974"),
    dict(key="benjamini1995fdr", type="article", authors=[("Yoav", "Benjamini"), ("Yosef", "Hochberg")],
         title="Controlling the false discovery rate: A practical and powerful approach to multiple testing",
         journal="Journal of the Royal Statistical Society: Series B (Methodological)", volume="57", number="1",
         pages="289–300", year="1995"),
    dict(key="hedges1981", type="article", authors=[("Larry V.", "Hedges")],
         title="Distribution theory for Glass's estimator of effect size and related estimators",
         journal="Journal of Educational Statistics", volume="6", number="2", pages="107–128", year="1981"),
    dict(key="grabe2002npvi", type="incollection", authors=[("Esther", "Grabe"), ("Ee Ling", "Low")],
         title="Durational variability in speech and the rhythm class hypothesis",
         booktitle="Laboratory Phonology 7", editors="C. Gussenhoven and N. Warner", publisher="Mouton de Gruyter",
         address="Berlin", pages="515–546", year="2002"),
    dict(key="krumhansl1990", type="book", authors=[("Carol L.", "Krumhansl")],
         title="Cognitive foundations of musical pitch", publisher="Oxford University Press", address="New York", year="1990"),
    dict(key="foscarin2024beatthis", type="inproceedings",
         authors=[("Francesco", "Foscarin"), ("Jan", "Schlüter"), ("Gerhard", "Widmer")],
         title="Beat this! Accurate beat tracking without DBN postprocessing",
         booktitle="Proceedings of the 25th International Society for Music Information Retrieval Conference", year="2024"),
    dict(key="sonicdiff", type="software", authors=[("Sasanka", "Boruah")],
         title="VU3INI SonicDiff: Cross-tradition vocal acoustic comparison", year="2026", version=VERSION,
         publisher="VU3INI"),
]

STYLES = ["IEEE", "ACS", "AIP", "APA 7", "MLA 9"]


def _ini(first):
    parts = first.replace("-", " ").split()
    return " ".join(p[0] + "." for p in parts if p)


def _au_ieee(a):
    names = [f"{_ini(f)} {l}" for f, l in a]
    if len(names) > 6:
        return names[0] + " et al."
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + (", and " if len(names) > 2 else " and ") + names[-1]


def _au_acs(a):
    return "; ".join(f"{l}, {_ini(f)}" for f, l in a)


def _au_aip(a):
    names = [f"{_ini(f)} {l}" for f, l in a]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + ", and " + names[-1]


def _au_apa(a):
    names = [f"{l}, {_ini(f)}" for f, l in a]
    if len(names) == 1:
        return names[0]
    if len(names) <= 20:
        return ", ".join(names[:-1]) + ", & " + names[-1]
    return ", ".join(names[:19]) + ", … " + names[-1]


def _au_mla(a):
    f, l = a[0]
    if len(a) == 1:
        return f"{l}, {f}"
    if len(a) == 2:
        return f"{l}, {f}, and {a[1][0]} {a[1][1]}"
    return f"{l}, {f}, et al"


def fmt(r, style):
    t, a, y = r["type"], r["authors"], r["year"]
    vol, num, pp = r.get("volume"), r.get("number"), r.get("pages")
    doi = f" doi: {r['doi']}." if r.get("doi") and style == "IEEE" else ""
    if style == "IEEE":
        if t == "article":
            s = f"{_au_ieee(a)}, “{r['title']},” *{r['journal']}*"
            s += f", vol. {vol}" if vol else ""
            s += f", no. {num}" if num else ""
            s += f", pp. {pp}" if pp else ""
            return s + f", {y}.{doi}"
        if t in ("inproceedings", "incollection"):
            s = f"{_au_ieee(a)}, “{r['title']},” in *{r['booktitle']}*"
            s += f", {r['address']}: {r['publisher']}" if r.get("publisher") and r.get("address") else ""
            return s + f", {y}" + (f", pp. {pp}." if pp else ".")
        if t == "book":
            return f"{_au_ieee(a)}, *{r['title']}*. {r.get('address', '')}: {r['publisher']}, {y}."
        return f"{_au_ieee(a)}, *{r['title']}*, ver. {r.get('version', '')}. {r.get('publisher', '')}, {y}." + \
            (f" [Online]. Available: {r['url']}" if r.get("url") else "")
    if style == "ACS":
        if t == "article":
            return f"{_au_acs(a)} {r['title']}. *{r['journal']}* **{y}**, *{vol}*" + (f" ({num})" if num else "") + \
                (f", {pp}." if pp else ".")
        if t in ("inproceedings", "incollection"):
            return f"{_au_acs(a)} {r['title']}. In *{r['booktitle']}*" + \
                (f"; {r['publisher']}: {r['address']}" if r.get("publisher") and r.get("address") else "") + \
                f", {y}" + (f"; pp {pp}." if pp else ".")
        if t == "book":
            return f"{_au_acs(a)} *{r['title']}*; {r['publisher']}: {r.get('address', '')}, {y}."
        return f"{_au_acs(a)} *{r['title']}*, version {r.get('version', '')}; {r.get('publisher', '')}, {y}." + \
            (f" {r['url']}" if r.get("url") else "")
    if style == "AIP":
        if t == "article":
            return f"{_au_aip(a)}, “{r['title']},” {r['journal']} **{vol}**, {pp.split('–')[0] if pp else ''} ({y})."
        if t in ("inproceedings", "incollection"):
            return f"{_au_aip(a)}, “{r['title']},” in *{r['booktitle']}*" + \
                (f" ({r['publisher']}, {r['address']}, {y})" if r.get("publisher") else f" ({y})") + \
                (f", pp. {pp}." if pp else ".")
        if t == "book":
            return f"{_au_aip(a)}, *{r['title']}* ({r['publisher']}, {r.get('address', '')}, {y})."
        return f"{_au_aip(a)}, *{r['title']}*, version {r.get('version', '')} ({r.get('publisher', '')}, {y})."
    if style == "APA 7":
        if t == "article":
            s = f"{_au_apa(a)} ({y}). {r['title']}. *{r['journal']}*"
            s += f", *{vol}*" if vol else ""
            s += f"({num})" if num else ""
            s += f", {pp}" if pp else ""
            return s + "." + (f" https://doi.org/{r['doi']}" if r.get("doi") else "")
        if t == "inproceedings":
            return f"{_au_apa(a)} ({y}). {r['title']}. In *{r['booktitle']}*" + (f" (pp. {pp})." if pp else ".")
        if t == "incollection":
            return f"{_au_apa(a)} ({y}). {r['title']}. In {r.get('editors', '')} (Eds.), *{r['booktitle']}* " \
                   f"(pp. {pp}). {r['publisher']}."
        if t == "book":
            return f"{_au_apa(a)} ({y}). *{r['title']}*. {r['publisher']}."
        return f"{_au_apa(a)} ({y}). *{r['title']}* (Version {r.get('version', '')}) [Computer software]. " \
               f"{r.get('publisher', '')}." + (f" {r['url']}" if r.get("url") else "")
    # MLA 9
    if t == "article":
        s = f"{_au_mla(a)}. “{r['title']}.” *{r['journal']}*"
        s += f", vol. {vol}" if vol else ""
        s += f", no. {num}" if num else ""
        s += f", {y}"
        s += f", pp. {pp}" if pp else ""
        return s + "." + (f" https://doi.org/{r['doi']}." if r.get("doi") else "")
    if t in ("inproceedings", "incollection"):
        return f"{_au_mla(a)}. “{r['title']}.” *{r['booktitle']}*" + \
            (f", edited by {r['editors']}, {r['publisher']}" if r.get("editors") else "") + f", {y}" + \
            (f", pp. {pp}." if pp else ".")
    if t == "book":
        return f"{_au_mla(a)}. *{r['title']}*. {r['publisher']}, {y}."
    return f"{_au_mla(a)}. *{r['title']}*. Version {r.get('version', '')}, {r.get('publisher', '')}, {y}."


def reference_list(style):
    if style not in STYLES:
        style = "APA 7"
    refs = REFS
    if style in ("APA 7", "MLA 9"):
        refs = sorted(REFS, key=lambda r: (r["authors"][0][1].lower(), r["year"]))
    items = [fmt(r, style) for r in refs]
    if style in ("IEEE", "ACS", "AIP"):
        return [f"[{i}] {s}" if style == "IEEE" else f"({i}) {s}" if style == "ACS" else f"{i}. {s}"
                for i, s in enumerate(items, 1)]
    return items


def bibtex():
    out = []
    for r in REFS:
        t = {"software": "misc"}.get(r["type"], r["type"])
        fields = {"author": " and ".join(f"{l}, {f}" for f, l in r["authors"]), "title": "{" + r["title"] + "}",
                  "year": r["year"]}
        for k in ("journal", "booktitle", "volume", "number", "publisher", "address", "doi", "url", "version"):
            if r.get(k):
                fields[k] = r[k]
        if r.get("pages"):
            fields["pages"] = r["pages"].replace("–", "--")
        if r.get("editors"):
            fields["editor"] = r["editors"].replace(" and ", " and ")
        body = ",\n".join(f"  {k} = {{{v}}}" if not v.startswith("{") else f"  {k} = {v}" for k, v in fields.items())
        out.append(f"@{t}{{{r['key']},\n{body}\n}}")
    return "\n\n".join(out) + "\n"
