"""
╔══════════════════════════════════════════════════════════════════════════════╗
║         CLASSEUR DE GESTION FINANCIÈRE  —  Version Web 1.0                  ║
║  Convertie de Tkinter vers Flask pour déploiement en ligne                  ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from flask import Flask, render_template, request, jsonify, send_file, make_response
import json, os, datetime, io
from collections import defaultdict
from pathlib import Path

# ── ReportLab (export PDF) ───────────────────────────────────────────────────
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                 TableStyle, HRFlowable, PageBreak)
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

app = Flask(__name__)

# ── Persistance ──────────────────────────────────────────────────────────────
DATA_FILE = os.environ.get('DATA_PATH', 'data.json')

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            d = json.load(f)
    else:
        d = {}
    d.setdefault('services', [])
    d.setdefault('biens', [])
    d.setdefault('sorties', [])
    d.setdefault('stock', [])
    d.setdefault('caisse', [])
    d.setdefault('budget', [])
    d.setdefault('entreprise', {
        'nom': 'Mon Entreprise', 'adresse': '',
        'telephone': '', 'email': '', 'nif': '',
    })
    return d

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def parse_date(s):
    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y'):
        try:
            return datetime.datetime.strptime(s.strip(), fmt).date()
        except (ValueError, AttributeError):
            pass
    return None

def get_month_key(date_str):
    d = parse_date(date_str)
    return d.strftime('%Y-%m') if d else '0000-00'

def monthly_totals(records):
    result = defaultdict(float)
    for r in records:
        mk = get_month_key(r.get('date', ''))
        result[mk] += float(r.get('montant', 0))
    return result

# ══════════════════════════════════════════════════════════════════════════════
# PAGE PRINCIPALE
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/')
def index():
    return render_template('index.html')

# ══════════════════════════════════════════════════════════════════════════════
# API — DONNÉES
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/data')
def get_all_data():
    return jsonify(load_data())

@app.route('/api/entreprise', methods=['POST'])
def update_entreprise():
    data = load_data()
    data['entreprise'] = request.json
    save_data(data)
    return jsonify({'ok': True})

# ── CRUD générique ─────────────────────────────────────────────────────────

def crud_add(key):
    data = load_data()
    rec = request.json
    data.setdefault(key, []).append(rec)
    save_data(data)
    return jsonify({'ok': True, 'data': data[key]})

def crud_delete(key, idx):
    data = load_data()
    try:
        data[key].pop(int(idx))
        save_data(data)
        return jsonify({'ok': True})
    except (IndexError, ValueError):
        return jsonify({'ok': False, 'error': 'Index invalide'}), 400

@app.route('/api/services', methods=['GET', 'POST'])
def services():
    if request.method == 'POST':
        return crud_add('services')
    return jsonify(load_data()['services'])

@app.route('/api/services/<int:idx>', methods=['DELETE'])
def service_delete(idx):
    return crud_delete('services', idx)

@app.route('/api/biens', methods=['GET', 'POST'])
def biens():
    if request.method == 'POST':
        data = load_data()
        rec = request.json
        qty = float(rec.get('extra', 0) or 1)
        desc = rec.get('description', '').lower()
        # Mise à jour stock
        for item in data.get('stock', []):
            if item.get('nom', '').lower() == desc:
                qte_cur = float(item.get('quantite', 0))
                item['quantite'] = max(0, qte_cur - qty)
                item.setdefault('mouvements', []).append({
                    'date': rec.get('date', ''),
                    'type': 'vente', 'quantite': -qty,
                    'montant': float(rec.get('montant', 0))
                })
                break
        data.setdefault('biens', []).append(rec)
        save_data(data)
        return jsonify({'ok': True, 'data': data['biens']})
    return jsonify(load_data()['biens'])

@app.route('/api/biens/<int:idx>', methods=['DELETE'])
def bien_delete(idx):
    return crud_delete('biens', idx)

@app.route('/api/sorties', methods=['GET', 'POST'])
def sorties():
    if request.method == 'POST':
        return crud_add('sorties')
    return jsonify(load_data()['sorties'])

@app.route('/api/sorties/<int:idx>', methods=['DELETE'])
def sortie_delete(idx):
    return crud_delete('sorties', idx)

@app.route('/api/caisse', methods=['GET', 'POST'])
def caisse():
    if request.method == 'POST':
        return crud_add('caisse')
    return jsonify(load_data()['caisse'])

@app.route('/api/caisse/<int:idx>', methods=['DELETE'])
def caisse_delete(idx):
    return crud_delete('caisse', idx)

@app.route('/api/budget', methods=['GET', 'POST'])
def budget():
    if request.method == 'POST':
        return crud_add('budget')
    return jsonify(load_data()['budget'])

@app.route('/api/budget/<int:idx>', methods=['DELETE'])
def budget_delete(idx):
    return crud_delete('budget', idx)

# ── STOCK ──────────────────────────────────────────────────────────────────

@app.route('/api/stock', methods=['GET', 'POST'])
def stock():
    if request.method == 'POST':
        data = load_data()
        rec = request.json
        nom = rec.get('nom', '').strip()
        qte = float(rec.get('quantite', 0))
        cout = float(rec.get('cout_unitaire', 0))
        # Réappro si existe déjà
        for item in data.get('stock', []):
            if item.get('nom', '').lower() == nom.lower():
                item['quantite'] = float(item.get('quantite', 0)) + qte
                item['cout_unitaire'] = cout
                item.setdefault('mouvements', []).append({
                    'date': rec.get('date_entree', ''),
                    'type': 'réappro', 'quantite': qte, 'montant': qte*cout
                })
                save_data(data)
                return jsonify({'ok': True, 'data': data['stock']})
        rec.setdefault('mouvements', [{'date': rec.get('date_entree', ''),
                                        'type': 'entrée initiale',
                                        'quantite': qte, 'montant': qte*cout}])
        data.setdefault('stock', []).append(rec)
        save_data(data)
        return jsonify({'ok': True, 'data': data['stock']})
    return jsonify(load_data()['stock'])

@app.route('/api/stock/<int:idx>', methods=['DELETE'])
def stock_delete(idx):
    return crud_delete('stock', idx)

@app.route('/api/stock/<int:idx>/adjust', methods=['POST'])
def stock_adjust(idx):
    data = load_data()
    try:
        item = data['stock'][idx]
        qty = float(request.json.get('quantite', 0))
        item['quantite'] = float(item.get('quantite', 0)) + qty
        item.setdefault('mouvements', []).append({
            'date': datetime.date.today().strftime('%d/%m/%Y'),
            'type': 'ajustement', 'quantite': qty,
            'montant': qty * float(item.get('cout_unitaire', 0))
        })
        save_data(data)
        return jsonify({'ok': True})
    except (IndexError, ValueError) as e:
        return jsonify({'ok': False, 'error': str(e)}), 400

# ── ANALYTICS ──────────────────────────────────────────────────────────────

@app.route('/api/analytics')
def analytics():
    data = load_data()
    svc   = sum(float(r.get('montant',0)) for r in data.get('services',[]))
    biens = sum(float(r.get('montant',0)) for r in data.get('biens',[]))
    sort  = sum(float(r.get('montant',0)) for r in data.get('sorties',[]))
    stock_val = sum(float(i.get('quantite',0)) * float(i.get('cout_unitaire',0))
                    for i in data.get('stock',[]))
    entrees = svc + biens

    # Analyse mensuelle (12 derniers mois)
    months_set = set()
    for key in ('services', 'biens', 'sorties'):
        for r in data.get(key, []):
            mk = get_month_key(r.get('date', ''))
            if mk != '0000-00':
                months_set.add(mk)

    sorted_months = sorted(months_set)[-12:]
    mc_svc  = monthly_totals(data.get('services', []))
    mc_bien = monthly_totals(data.get('biens', []))
    mc_sort = monthly_totals(data.get('sorties', []))

    monthly = []
    for mk in sorted_months:
        try:
            label = datetime.datetime.strptime(mk, '%Y-%m').strftime('%b %Y')
        except ValueError:
            label = mk
        e = mc_svc.get(mk,0) + mc_bien.get(mk,0)
        s = mc_sort.get(mk,0)
        monthly.append({'mois': mk, 'label': label, 'entrees': e, 'sorties': s, 'net': e-s})

    # Caisse
    caisse = data.get('caisse', [])
    entrees_c = sum(float(r.get('montant',0)) for r in caisse if r.get('type') == 'entrée')
    sorties_c = sum(float(r.get('montant',0)) for r in caisse if r.get('type') == 'sortie')

    # Budget vs Réel
    reel_map = defaultdict(float)
    for rec in data.get('sorties', []):
        mk = get_month_key(rec.get('date',''))
        try:
            d = datetime.datetime.strptime(mk, '%Y-%m')
            mois_lbl = d.strftime('%m/%Y')
        except ValueError:
            mois_lbl = mk
        cat = (rec.get('categorie','') or 'Autres').strip()
        reel_map[(mois_lbl, cat)] += float(rec.get('montant',0))

    budget_rows = []
    for bgt in data.get('budget', []):
        mois = bgt.get('mois','')
        cat  = bgt.get('categorie','')
        prev = float(bgt.get('prevu', 0))
        reel = reel_map.get((mois, cat), 0.0)
        ecart = reel - prev
        taux  = (reel / prev * 100) if prev > 0 else 0.0
        budget_rows.append({'mois':mois,'categorie':cat,'prevu':prev,
                             'reel':reel,'ecart':ecart,'taux':round(taux,1)})

    return jsonify({
        'kpis': {
            'services': svc, 'biens': biens, 'sorties': sort,
            'stock': stock_val, 'entrees': entrees, 'solde': entrees - sort
        },
        'monthly': monthly,
        'caisse': {'entrees': entrees_c, 'sorties': sorties_c, 'solde': entrees_c - sorties_c},
        'budget_rows': budget_rows,
        'low_stock': [i for i in data.get('stock',[]) if float(i.get('quantite',0)) <= 10],
    })

# ══════════════════════════════════════════════════════════════════════════════
# EXPORT PDF
# ══════════════════════════════════════════════════════════════════════════════

def build_pdf_rapport(data):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                             topMargin=2*cm, bottomMargin=2*cm,
                             leftMargin=2*cm, rightMargin=2*cm)
    VERT  = colors.HexColor('#1A6B3C')
    BLEU  = colors.HexColor('#154360')
    ROUGE = colors.HexColor('#922B21')
    OR    = colors.HexColor('#B7770D')
    VIOLET= colors.HexColor('#5B2C8D')
    GRIS  = colors.HexColor('#F0F3F8')
    GRIS2 = colors.HexColor('#D8DCE5')
    NOIR  = colors.HexColor('#1C2833')

    styles = getSampleStyleSheet()
    s_title  = ParagraphStyle('t',  parent=styles['Normal'], fontSize=22, textColor=BLEU,
                               fontName='Helvetica-Bold', alignment=TA_LEFT, spaceAfter=4)
    s_h2     = ParagraphStyle('h2', parent=styles['Normal'], fontSize=13, textColor=BLEU,
                               fontName='Helvetica-Bold', spaceBefore=14, spaceAfter=6)
    s_normal = ParagraphStyle('n',  parent=styles['Normal'], fontSize=9, fontName='Helvetica', textColor=NOIR)
    s_bold   = ParagraphStyle('b',  parent=styles['Normal'], fontSize=9, fontName='Helvetica-Bold', textColor=NOIR)
    s_right  = ParagraphStyle('r',  parent=styles['Normal'], fontSize=9, fontName='Helvetica', textColor=NOIR, alignment=TA_RIGHT)
    s_center = ParagraphStyle('c',  parent=styles['Normal'], fontSize=9, fontName='Helvetica', textColor=NOIR, alignment=TA_CENTER)
    s_sub    = ParagraphStyle('s',  parent=styles['Normal'], fontSize=10, textColor=colors.HexColor('#717D86'), fontName='Helvetica')

    ent = data.get('entreprise', {})
    now = datetime.datetime.now()
    story = []

    # En-tête
    hdr_data = [[
        Paragraph(f"<b>{ent.get('nom','Mon Entreprise')}</b>", s_title),
        Paragraph(f"<b>RAPPORT FINANCIER</b><br/>Généré le {now.strftime('%d/%m/%Y à %H:%M')}",
                  ParagraphStyle('rh', parent=styles['Normal'], fontSize=11, textColor=BLEU,
                                 fontName='Helvetica-Bold', alignment=TA_RIGHT))
    ]]
    hdr_tbl = Table(hdr_data, colWidths=[10*cm, 7.7*cm])
    hdr_tbl.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'BOTTOM'),('BOTTOMPADDING',(0,0),(0,-1),20)]))
    story.append(hdr_tbl)

    infos = []
    for k, lbl in [('adresse','Adresse'),('telephone','Tél'),('email','Email'),('nif','NIF')]:
        v = ent.get(k,'').strip()
        if v: infos.append(f'{lbl} : {v}')
    if infos: story.append(Paragraph('  |  '.join(infos), s_sub))
    story.append(HRFlowable(width='100%', thickness=2, color=BLEU, spaceAfter=12, spaceBefore=8))

    # Bilan
    svc  = sum(float(r.get('montant',0)) for r in data.get('services',[]))
    bien = sum(float(r.get('montant',0)) for r in data.get('biens',[]))
    sort = sum(float(r.get('montant',0)) for r in data.get('sorties',[]))
    entrees = svc + bien
    solde   = entrees - sort
    stock_val = sum(float(i.get('quantite',0))*float(i.get('cout_unitaire',0))
                    for i in data.get('stock',[]))

    story.append(Paragraph('BILAN GLOBAL', s_h2))
    bilan_rows = [
        ['', 'LIBELLÉ', 'MONTANT (BIF)'],
        ['ENTRÉES', 'Services Rendus', f'{svc:,.0f}'],
        ['', 'Biens Vendus', f'{bien:,.0f}'],
        ['', 'Total Entrées', f'{entrees:,.0f}'],
        ['SORTIES', 'Dépenses & Charges', f'{sort:,.0f}'],
        ['STOCK', 'Valeur totale stock', f'{stock_val:,.0f}'],
        ['RÉSULTAT', 'Bénéfice / Perte NET', f"{'+' if solde>=0 else ''}{solde:,.0f}"],
    ]
    bilan_tbl = Table(bilan_rows, colWidths=[3.5*cm, 9*cm, 5.2*cm])
    bilan_tbl.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),BLEU),('TEXTCOLOR',(0,0),(-1,0),colors.white),
        ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),9),
        ('ALIGN',(2,0),(2,-1),'RIGHT'),('GRID',(0,0),(-1,-1),0.4,GRIS2),
        ('BACKGROUND',(0,3),(-1,3),colors.HexColor('#D0EBD9')),
        ('FONTNAME',(0,3),(-1,3),'Helvetica-Bold'),
        ('BACKGROUND',(0,6),(-1,6),
            colors.HexColor('#D0EBD9') if solde>=0 else colors.HexColor('#FDECEA')),
        ('FONTNAME',(0,6),(-1,6),'Helvetica-Bold'),
        ('TEXTCOLOR',(2,6),(2,6), VERT if solde>=0 else ROUGE),
        ('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),
        ('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),
    ]))
    story.append(bilan_tbl)
    story.append(Spacer(1,14))

    # Historique
    story.append(HRFlowable(width='100%', thickness=0.5, color=GRIS2, spaceAfter=8))
    story.append(Paragraph('LIVRE JOURNAL — HISTORIQUE DES MOUVEMENTS', s_h2))

    all_recs = []
    for key, label, side in [('services','Services Rendus','credit'),
                               ('biens','Biens Vendus','credit'),
                               ('sorties','Dépenses','debit')]:
        for rec in data.get(key,[]):
            all_recs.append((label, side, rec))
    all_recs.sort(key=lambda x: (parse_date(x[2].get('date','')) or datetime.date.min))

    hist_rows = [[
        Paragraph('<b>N°</b>', s_center), Paragraph('<b>Date</b>', s_center),
        Paragraph('<b>Type</b>', s_center), Paragraph('<b>Description</b>', s_bold),
        Paragraph('<b>Réf./Client</b>', s_normal),
        Paragraph('<b>DÉBIT (BIF)</b>', s_right), Paragraph('<b>CRÉDIT (BIF)</b>', s_right),
    ]]
    td = tc = 0.0
    for i, (label, side, rec) in enumerate(all_recs, 1):
        m = float(rec.get('montant',0))
        if side=='debit': deb,cre=f'{m:,.0f}',''; td+=m
        else: deb,cre='',f'{m:,.0f}'; tc+=m
        hist_rows.append([
            Paragraph(str(i),s_center), Paragraph(rec.get('date',''),s_center),
            Paragraph(label[:14],s_center),
            Paragraph((rec.get('description','') or '')[:40],s_normal),
            Paragraph((rec.get('client','') or '')[:22],s_normal),
            Paragraph(deb,s_right), Paragraph(cre,s_right),
        ])
    net = tc - td
    s_tot = ParagraphStyle('st', parent=styles['Normal'], fontSize=9, fontName='Helvetica-Bold', alignment=TA_RIGHT)
    hist_rows.append(['','','',Paragraph('<b>TOTAUX</b>',s_bold),'',
                      Paragraph(f'<b>{td:,.0f}</b>',s_tot), Paragraph(f'<b>{tc:,.0f}</b>',s_tot)])
    hist_rows.append(['','','',Paragraph('<b>SOLDE NET</b>',s_bold),'','',
                      Paragraph(f'<b>{net:,.0f}</b>',
                                ParagraphStyle('sn',parent=styles['Normal'],fontSize=9,
                                               fontName='Helvetica-Bold',alignment=TA_RIGHT,
                                               textColor=VERT if net>=0 else ROUGE))])
    hist_tbl = Table(hist_rows, colWidths=[1.2*cm,2.2*cm,2.8*cm,5.5*cm,3.3*cm,2.8*cm,2.8*cm])
    n = len(hist_rows)
    ts = [
        ('BACKGROUND',(0,0),(-1,0),BLEU),('TEXTCOLOR',(0,0),(-1,0),colors.white),
        ('FONTSIZE',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),4),
        ('BOTTOMPADDING',(0,0),(-1,-1),4),('LEFTPADDING',(0,0),(-1,-1),5),
        ('RIGHTPADDING',(0,0),(-1,-1),5),('GRID',(0,0),(-1,-2),0.3,GRIS2),
        ('LINEABOVE',(0,n-2),(-1,n-2),1.2,BLEU),
        ('BACKGROUND',(0,n-2),(-1,n-2),GRIS),
        ('BACKGROUND',(0,n-1),(-1,n-1),
            colors.HexColor('#D0EBD9') if net>=0 else colors.HexColor('#FDECEA')),
    ]
    for ri in range(1,n-2):
        if ri%2==0: ts.append(('BACKGROUND',(0,ri),(-1,ri),GRIS))
    hist_tbl.setStyle(TableStyle(ts))
    story.append(hist_tbl)
    story.append(Spacer(1,14))

    # Stock
    stock_items = data.get('stock',[])
    if stock_items:
        story.append(PageBreak())
        story.append(Paragraph('ÉTAT DU STOCK', s_h2))
        stk_hdr = [Paragraph(f'<b>{h}</b>',s_bold) for h in
                   ['Article','Catégorie','Qté','Coût unit. (BIF)','Valeur tot. (BIF)','Statut']]
        stk_rows = [stk_hdr]
        for item in stock_items:
            qte=float(item.get('quantite',0)); cout=float(item.get('cout_unitaire',0))
            statut = 'VIDE' if qte<=0 else ('FAIBLE' if qte<=10 else 'OK')
            stk_rows.append([
                Paragraph(item.get('nom',''),s_normal),
                Paragraph(item.get('categorie',''),s_normal),
                Paragraph(f'{qte:.0f}',s_center),
                Paragraph(f'{cout:,.0f}',s_right),
                Paragraph(f'{qte*cout:,.0f}',s_right),
                Paragraph(statut,s_center),
            ])
        stk_tbl = Table(stk_rows, colWidths=[4.5*cm,3*cm,2.5*cm,3.5*cm,3.5*cm,2.2*cm])
        stk_tbl.setStyle(TableStyle([
            ('BACKGROUND',(0,0),(-1,0),VIOLET),('TEXTCOLOR',(0,0),(-1,0),colors.white),
            ('FONTSIZE',(0,0),(-1,-1),8),('GRID',(0,0),(-1,-1),0.3,GRIS2),
            ('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4),
        ]))
        story.append(stk_tbl)

    # Pied
    story.append(Spacer(1,100))
    story.append(HRFlowable(width='100%',thickness=1,color=BLEU,spaceAfter=6))
    story.append(Paragraph(
        f"Document généré automatiquement — Classeur de Gestion v1.0 Web — {now.strftime('%d/%m/%Y à %H:%M')}",
        ParagraphStyle('ft',parent=styles['Normal'],fontSize=7,
                       textColor=colors.HexColor('#717D86'),
                       fontName='Helvetica',alignment=TA_CENTER)
    ))

    doc.build(story)
    buffer.seek(0)
    return buffer

@app.route('/api/pdf/rapport')
def pdf_rapport():
    data = load_data()
    buf = build_pdf_rapport(data)
    nom = data.get('entreprise',{}).get('nom','rapport').replace(' ','_')
    today = datetime.date.today().strftime('%Y%m%d')
    return send_file(buf, as_attachment=True,
                     download_name=f'rapport_{nom}_{today}.pdf',
                     mimetype='application/pdf')

@app.route('/api/pdf/facture')
def pdf_facture():
    data = load_data()
    buffer = io.BytesIO()
    all_recs = data.get('services',[]) + data.get('biens',[])
    all_recs.sort(key=lambda r: (parse_date(r.get('date','')) or datetime.date.min))

    doc = SimpleDocTemplate(buffer, pagesize=A4,
                             topMargin=2*cm,bottomMargin=2*cm,
                             leftMargin=2*cm,rightMargin=2*cm)
    BLEU=colors.HexColor('#154360'); VERT=colors.HexColor('#1A6B3C')
    ROUGE=colors.HexColor('#922B21'); GRIS=colors.HexColor('#F0F3F8')
    GRIS2=colors.HexColor('#D8DCE5')
    styles=getSampleStyleSheet()
    s_n=ParagraphStyle('n',parent=styles['Normal'],fontSize=9,fontName='Helvetica')
    s_r=ParagraphStyle('r',parent=styles['Normal'],fontSize=9,fontName='Helvetica',alignment=TA_RIGHT)
    s_c=ParagraphStyle('c',parent=styles['Normal'],fontSize=9,fontName='Helvetica',alignment=TA_CENTER)
    s_b=ParagraphStyle('b',parent=styles['Normal'],fontSize=9,fontName='Helvetica-Bold')

    ent=data.get('entreprise',{}); now=datetime.datetime.now(); story=[]
    story.append(Paragraph(f"<b>{ent.get('nom','Mon Entreprise')}</b>",
                            ParagraphStyle('ht',parent=styles['Normal'],fontSize=20,
                                           textColor=BLEU,fontName='Helvetica-Bold')))
    story.append(Spacer(1,4))
    story.append(HRFlowable(width='100%',thickness=2,color=BLEU,spaceBefore=8,spaceAfter=14))
    info_data=[[
        Paragraph('<b>FACTURE</b>',ParagraphStyle('ti',parent=styles['Normal'],fontSize=18,
                  fontName='Helvetica-Bold',textColor=BLEU)),
        Paragraph(f"N° : <b>{len(all_recs):04d}</b><br/>Date : {now.strftime('%d/%m/%Y')}",
                  ParagraphStyle('di',parent=styles['Normal'],fontSize=10,alignment=TA_RIGHT))
    ]]
    info_tbl=Table(info_data,colWidths=[9*cm,8.7*cm])
    info_tbl.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP')]))
    story.append(info_tbl); story.append(Spacer(1,16))

    hdr=[Paragraph('<b>N°</b>',s_c),Paragraph('<b>Description</b>',s_b),
         Paragraph('<b>Client</b>',s_b),Paragraph('<b>Catégorie</b>',s_b),
         Paragraph('<b>Date</b>',s_c),Paragraph('<b>Montant (BIF)</b>',s_r)]
    rows=[hdr]; total=0.0
    for i,rec in enumerate(all_recs,1):
        m=float(rec.get('montant',0)); total+=m
        rows.append([Paragraph(str(i),s_c),
                     Paragraph((rec.get('description','') or '')[:45],s_n),
                     Paragraph((rec.get('client','') or '')[:30],s_n),
                     Paragraph((rec.get('categorie','') or '')[:25],s_n),
                     Paragraph(rec.get('date',''),s_c),
                     Paragraph(f'{m:,.0f}',s_r)])
    rows.append(['','','','',Paragraph('<b>TOTAL</b>',s_b),
                 Paragraph(f'<b>{total:,.0f}</b>',
                            ParagraphStyle('tot',parent=styles['Normal'],fontSize=11,
                                           fontName='Helvetica-Bold',textColor=VERT,alignment=TA_RIGHT))])
    tbl=Table(rows,colWidths=[1.2*cm,5.5*cm,3.5*cm,2.8*cm,2.5*cm,3.2*cm])
    nr=len(rows)
    tbl.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),BLEU),('TEXTCOLOR',(0,0),(-1,0),colors.white),
        ('FONTSIZE',(0,0),(-1,-1),8),('GRID',(0,0),(-1,-2),0.3,GRIS2),
        ('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),
        ('LINEABOVE',(0,nr-1),(-1,nr-1),1.5,BLEU),
        ('BACKGROUND',(0,nr-1),(-1,nr-1),colors.HexColor('#E3F5EC')),
    ]+[('BACKGROUND',(0,i),(-1,i),GRIS) for i in range(1,nr-1) if i%2==0]))
    story.append(tbl)
    doc.build(story)
    buffer.seek(0)
    nom=ent.get('nom','facture').replace(' ','_')
    today=datetime.date.today().strftime('%Y%m%d')
    return send_file(buffer,as_attachment=True,
                     download_name=f'facture_{nom}_{today}.pdf',
                     mimetype='application/pdf')

# ══════════════════════════════════════════════════════════════════════════════
# POINT D'ENTRÉE
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV', 'production') != 'production'
    app.run(host='0.0.0.0', port=port, debug=debug)
