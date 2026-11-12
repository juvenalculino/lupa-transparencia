import io
from datetime import datetime
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)


_COR_TITULO = colors.HexColor("#15324b")
_COR_DESTAQUE = colors.HexColor("#eaf1f7")
_COR_LINHA = colors.HexColor("#cbd5e1")


def _texto(valor):
    if valor is None or valor == "":
        return "Não informado"
    return escape(str(valor)).replace("\n", "<br/>")


def _competencia(valor):
    valor = str(valor or "")
    if len(valor) == 6 and valor.isdigit():
        return f"{valor[4:6]}/{valor[:4]}"
    return valor or "Não informada"


def _moeda(valor):
    if valor is None or valor == "":
        return "Não informado"
    formatado = f"{float(valor):,.2f}"
    return "R$ " + formatado.replace(",", "_").replace(".", ",").replace("_", ".")


def gerar_relatorio_cruzamento_pdf(
        municipio, uf, codigo_ibge, dados, situacoes_cadastrais=None,
        filtros=None):
    filtros = filtros or {}
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=20 * mm,
        bottomMargin=18 * mm,
        title=f"Beneficiários e sócios - {municipio}/{uf}",
        author="Painel de Benefícios",
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="ReportTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=17,
        leading=21,
        textColor=_COR_TITULO,
        alignment=TA_CENTER,
        spaceAfter=8,
    ))
    styles.add(ParagraphStyle(
        name="SectionHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=_COR_TITULO,
        spaceBefore=9,
        spaceAfter=5,
    ))
    styles.add(ParagraphStyle(
        name="PersonHeading",
        parent=styles["Heading3"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=13,
        textColor=_COR_TITULO,
        spaceBefore=7,
        spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="SmallBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8,
        leading=11,
        spaceAfter=3,
    ))
    styles.add(ParagraphStyle(
        name="TableBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=7.5,
        leading=10,
    ))
    styles.add(ParagraphStyle(
        name="TableLabel",
        parent=styles["BodyText"],
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=10,
    ))

    def paragraph(value, style="SmallBody", markup=False):
        return Paragraph(
            str(value) if markup else _texto(value),
            styles[style],
        )

    story = [
        Paragraph("Beneficiários que também constam como sócios", styles["ReportTitle"]),
        paragraph(
            f"Município: <b>{_texto(municipio)}/{_texto(uf)}</b> · "
            f"Código IBGE: <b>{_texto(codigo_ibge)}</b>",
            markup=True,
        ),
        paragraph(f"Relatório gerado em: {datetime.now().astimezone().strftime('%d/%m/%Y %H:%M')}"),
        paragraph(
            "Situações cadastrais: "
            + (
                ", ".join(
                    "Não informada"
                    if situacao == "__SEM_SITUACAO__"
                    else situacao
                    for situacao in situacoes_cadastrais
                )
                if situacoes_cadastrais
                else "Todas"
            )
        ),
        paragraph(
            f"Programa do benefício: {filtros.get('programa') or 'Todos'}"
        ),
    ]
    if filtros.get("busca"):
        story.append(paragraph(f"Busca por empresa/CNPJ: {filtros['busca']}"))
    faixa_capital = []
    if filtros.get("capital_min") is not None:
        faixa_capital.append(f"a partir de {_moeda(filtros['capital_min'])}")
    if filtros.get("capital_max") is not None:
        faixa_capital.append(f"até {_moeda(filtros['capital_max'])}")
    if faixa_capital:
        story.append(paragraph(
            "Capital social: " + " ".join(faixa_capital)))
    if dados.get("coletado_em"):
        story.append(paragraph(
            f"Dados empresariais atualizados em: {_texto(dados['coletado_em'])}"
        ))
    if dados.get("origem"):
        story.append(paragraph(f"Fonte da coleta: {_texto(dados['origem'])}"))

    resumo = Table(
        [[
            paragraph(
                (
                    f"<b>{int(dados.get('beneficiarios_com_cnpj', 0)):,}</b>"
                    "<br/>beneficiários correspondentes"
                ).replace(",", "."),
                "TableBody",
                markup=True,
            ),
            paragraph(
                (
                    f"<b>{int(dados.get('empresas', 0)):,}</b>"
                    "<br/>empresas cadastradas"
                ).replace(",", "."),
                "TableBody",
                markup=True,
            ),
            paragraph(
                (
                    f"<b>{int(dados.get('socios', 0)):,}</b>"
                    "<br/>sócios cadastrados"
                ).replace(",", "."),
                "TableBody",
                markup=True,
            ),
        ]],
        colWidths=[58 * mm, 58 * mm, 58 * mm],
    )
    resumo.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _COR_DESTAQUE),
        ("BOX", (0, 0), (-1, -1), 0.5, _COR_LINHA),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, _COR_LINHA),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.extend([
        Spacer(1, 5 * mm),
        resumo,
        Paragraph("Critério e interpretação", styles["SectionHeading"]),
        paragraph(
            "A correspondência exige coincidência entre o nome normalizado e os "
            "seis dígitos visíveis do CPF mascarado. O resultado é indicativo: "
            "não comprova identidade, irregularidade ou relação entre o benefício "
            "e o capital social da empresa."
        ),
    ])

    resultados = dados.get("resultados", [])
    if not resultados:
        story.append(Paragraph(
            "Nenhum beneficiário com correspondência forte foi encontrado para "
            "este município.",
            styles["SectionHeading"],
        ))

    campos_empresa = [
        ("Razão social", "razao_social"),
        ("Nome fantasia", "nome_fantasia"),
        ("CNPJ", "cnpj"),
        ("Situação cadastral", "situacao_cadastral"),
        ("Capital social", "capital_social"),
        ("CNAE fiscal", "cnae_fiscal"),
        ("Descrição CNAE", "cnae_descricao"),
        ("Porte", "porte"),
        ("Endereço", "endereco"),
        ("Logradouro", "logradouro"),
        ("Número", "numero"),
        ("Complemento", "complemento"),
        ("Bairro", "bairro"),
        ("CEP", "cep"),
        ("Telefone", "telefone"),
        ("Cadastro atualizado em", "atualizado_em"),
        ("Sócio correspondente", "socio_nome"),
        ("CPF/CNPJ mascarado do sócio", "socio_cpf_cnpj_mascarado"),
        ("Qualificação do sócio", "socio_qualificacao"),
        ("Tipo de sócio", "socio_tipo"),
        ("Data de entrada", "socio_data_entrada"),
        ("Faixa etária", "socio_faixa_etaria"),
    ]

    for indice, pessoa in enumerate(resultados, start=1):
        story.append(Paragraph(
            f"Beneficiário {indice}: {_texto(pessoa.get('nome'))}",
            styles["PersonHeading"],
        ))
        story.append(paragraph(
            f"CPF mascarado: {_texto(pessoa.get('cpf_mascarado'))}"
        ))
        story.append(paragraph(
            "Programas: " + ", ".join(pessoa.get("programas", []))
        ))

        beneficios = pessoa.get("beneficios", [])
        if beneficios:
            tabela_beneficios = [[
                paragraph("Programa", "TableLabel"),
                paragraph("Competência", "TableLabel"),
                paragraph("Valor registrado", "TableLabel"),
            ]]
            for beneficio in beneficios:
                tabela_beneficios.append([
                    paragraph(beneficio.get("programa"), "TableBody"),
                    paragraph(_competencia(beneficio.get("competencia")), "TableBody"),
                    paragraph(_moeda(beneficio.get("valor")), "TableBody"),
                ])
            tabela = Table(
                tabela_beneficios,
                colWidths=[90 * mm, 38 * mm, 46 * mm],
                repeatRows=1,
            )
            tabela.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), _COR_DESTAQUE),
                ("GRID", (0, 0), (-1, -1), 0.4, _COR_LINHA),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            story.append(tabela)
        else:
            story.append(paragraph(
                "Períodos registrados: " + ", ".join(
                    _competencia(periodo) for periodo in pessoa.get("periodos", [])
                )
            ))

        for numero_empresa, empresa in enumerate(pessoa.get("empresas", []), start=1):
            story.append(Paragraph(
                f"Empresa relacionada {numero_empresa}",
                styles["SectionHeading"],
            ))
            linhas = [
                [paragraph(rotulo, "TableLabel"), paragraph(
                    _moeda(empresa.get(campo))
                    if campo == "capital_social"
                    else empresa.get(campo),
                    "TableBody",
                )]
                for rotulo, campo in campos_empresa
            ]
            detalhes = Table(
                linhas,
                colWidths=[55 * mm, 119 * mm],
                splitByRow=1,
            )
            detalhes.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (0, -1), _COR_DESTAQUE),
                ("GRID", (0, 0), (-1, -1), 0.35, _COR_LINHA),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]))
            story.extend([detalhes, Spacer(1, 3 * mm)])

    def rodape(canvas, documento):
        canvas.saveState()
        canvas.setStrokeColor(_COR_LINHA)
        canvas.line(
            documento.leftMargin,
            13 * mm,
            A4[0] - documento.rightMargin,
            13 * mm,
        )
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#475569"))
        canvas.drawString(
            documento.leftMargin, 9 * mm,
            f"Painel de Benefícios · {municipio}/{uf} · Código IBGE {codigo_ibge}",
        )
        canvas.drawRightString(
            A4[0] - documento.rightMargin, 9 * mm,
            f"Página {documento.page}",
        )
        canvas.restoreState()

    doc.build(story, onFirstPage=rodape, onLaterPages=rodape)
    return buffer.getvalue()
