import os
import tempfile
import base64
import io
import streamlit as st
from PIL import Image
from supabase import create_client, Client
from dotenv import load_dotenv
from fpdf import FPDF

# Carrega as variáveis do arquivo .env (apenas quando rodar localmente)
load_dotenv()

# ==========================================
# CONFIGURAÇÃO DA PÁGINA E VARIÁVEIS DE SESSÃO
# ==========================================
st.set_page_config(page_title="Precificador 3D Pro", page_icon="🖨️", layout="wide")

if 'carrinho' not in st.session_state:
    st.session_state.carrinho = []

# ==========================================
# CONEXÃO COM SUPABASE
# ==========================================
try:
    SUPABASE_URL = os.getenv("SUPABASE_URL") or st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = os.getenv("SUPABASE_KEY") or st.secrets["SUPABASE_KEY"]
except KeyError:
    st.error("⚠️ Chaves do Supabase não encontradas! Verifique seu arquivo .env ou Secrets.")
    st.stop()

@st.cache_resource
def init_connection():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_connection()

# ==========================================
# FUNÇÕES DE BANCO DE DADOS E PDF
# ==========================================
def listar_filamentos():
    return supabase.table("filamentos").select("*").execute().data

def obter_configuracoes():
    return supabase.table("configuracoes").select("*").eq("id", 1).execute().data[0]

def listar_orcamentos():
    # Retorna a lista ordenada alfabéticamente pelo nome da peça
    dados = supabase.table("orcamentos").select("*").order("nome_peca", desc=False).execute().data
    return dados

def criar_pdf_orcamento_multiplo(carrinho, valor_total):
    pdf = FPDF()
    pdf.add_page()
    
    pdf.set_font("Arial", 'B', 18)
    pdf.cell(w=0, h=15, txt="ORCAMENTO DE IMPRESSAO 3D", ln=1, align='C')
    pdf.line(10, 25, 200, 25)
    pdf.ln(5)
    
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(90, 10, txt="Produto", border=1)
    pdf.cell(20, 10, txt="Qtd", border=1, align='C')
    pdf.cell(40, 10, txt="V. Unitario", border=1, align='C')
    pdf.cell(40, 10, txt="Subtotal", border=1, align='C')
    pdf.ln()
    
    pdf.set_font("Arial", '', 12)
    for item in carrinho:
        nome_curto = item['nome'][:25] + "..." if len(item['nome']) > 25 else item['nome']
        pdf.cell(90, 10, txt=nome_curto, border=1)
        pdf.cell(20, 10, txt=str(item['quantidade']), border=1, align='C')
        pdf.cell(40, 10, txt=f"R$ {item['preco_unit']:.2f}", border=1, align='C')
        pdf.cell(40, 10, txt=f"R$ {item['subtotal']:.2f}", border=1, align='C')
        pdf.ln()
        
    pdf.ln(10)
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(w=0, h=10, txt=f"TOTAL A PAGAR: R$ {valor_total:.2f}", ln=1, align='R')
    
    pdf.ln(20)
    pdf.set_font("Arial", 'I', 10)
    pdf.cell(w=0, h=10, txt="Orcamento valido por 15 dias. Obrigado pela preferencia!", ln=1, align='C')
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        pdf.output(tmp.name)
        with open(tmp.name, "rb") as f:
            pdf_bytes = f.read()
            
    return pdf_bytes

# ==========================================
# INTERFACE DO USUÁRIO
# ==========================================
st.title("🖨️ Precificador 3D Pro")

lista_filamentos = listar_filamentos()

aba_calculadora, aba_pdv, aba_produtos, aba_filamentos, aba_configuracoes = st.tabs(
    ["💰 Calculadora", "🛒 PDV (Caixa)", "📦 Produtos", "🧵 Filamentos", "⚙️ Configurações"]
)

# ------------------------------------------
# ABA 1: CALCULADORA
# ------------------------------------------
with aba_calculadora:
    st.header("Calcular Novo Produto")
    if not lista_filamentos:
        st.warning("Cadastre um filamento na aba 'Filamentos' primeiro!")
    else:
        col_nome, col_foto = st.columns(2)
        with col_nome:
            nome_peca = st.text_input("Nome do Produto (opcional):", placeholder="Ex: Vaso Groot 15cm")
            opcoes_filamentos = {f"{f['material']} {f['cor']}": f for f in lista_filamentos}
            filamento_selecionado = st.selectbox("Filamento usado:", options=list(opcoes_filamentos.keys()))
        with col_foto:
            imagem_upload = st.file_uploader("Foto do Produto (opcional)", type=["png", "jpg", "jpeg"])
        
        st.markdown("### Dados da Impressão")
        col1, col2 = st.columns(2)
        with col1:
            peso_g = st.number_input("Peso do modelo (gramas)", min_value=0.1, value=50.0, step=1.0)
            tempo_min = st.number_input("Tempo de impressão (minutos)", min_value=1, value=120, step=10)
        with col2:
            tempo_operador = st.number_input("Seu tempo de trabalho (minutos)", min_value=0, value=15, step=5)
            margem_lucro = st.number_input("Lucro Desejado (%)", min_value=0, value=150, step=10)
            
        if st.button("Calcular Preço Final", type="primary", use_container_width=True):
            config = obter_configuracoes()
            filamento = opcoes_filamentos[filamento_selecionado]
            
            taxa_falhas = float(config.get('taxa_falhas_pct', 10.0))
            peso_com_perda = peso_g * (1 + (taxa_falhas / 100))
            custo_material = (peso_com_perda / 1000) * filamento['preco_por_kg']
            
            tempo_horas = tempo_min / 60
            potencia_kw = float(config['potencia_impressora_watts']) / 1000
            custo_energia = potencia_kw * tempo_horas * float(config['preco_kwh'])
            
            custo_desgaste = tempo_horas * float(config.get('custo_desgaste_por_hora', 0.50))
            custo_mao_obra = (tempo_operador / 60) * float(config.get('valor_hora_operador', 30.00))
            
            custo_total = custo_material + custo_energia + custo_desgaste + custo_mao_obra
            valor_lucro = custo_total * (margem_lucro / 100)
            preco_final = custo_total + valor_lucro
            
            if nome_peca.strip():
                img_b64 = None
                if imagem_upload is not None:
                    img = Image.open(imagem_upload)
                    if img.mode in ("RGBA", "P"): 
                        img = img.convert("RGB")
                    img.thumbnail((400, 400))
                    buffered = io.BytesIO()
                    img.save(buffered, format="JPEG", quality=85)
                    img_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")

                dados_pdv = {
                    "nome_peca": nome_peca.strip(),
                    "filamento_usado": filamento_selecionado,
                    "peso_g": peso_g,
                    "tempo_minutos": tempo_min,
                    "custo_total": custo_total,
                    "preco_final": preco_final,
                    "imagem_base64": img_b64
                }
                supabase.table("orcamentos").insert(dados_pdv).execute()
                st.toast("✅ Produto e foto salvos no catálogo!")
            
            st.divider()
            st.subheader("📊 Detalhamento dos Custos Reais")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Material", f"R\$ {custo_material:.2f}")
            m2.metric("Energia", f"R\$ {custo_energia:.2f}")
            m3.metric("Desgaste", f"R\$ {custo_desgaste:.2f}")
            m4.metric("Mão de Obra", f"R\$ {custo_mao_obra:.2f}")
            
            st.info(f"**Custo Total de Produção:** R\$ {custo_total:.2f}")
            st.success(f"🎯 **PREÇO FINAL SUGERIDO:** R\$ {preco_final:.2f} (Lucro: R\$ {valor_lucro:.2f})")

# ------------------------------------------
# ABA 2: FRENTE DE CAIXA (PDV)
# ------------------------------------------
with aba_pdv:
    st.header("🛒 Ponto de Venda")
    
    col_carrinho, espaco, col_produtos = st.columns([1.2, 0.1, 1])
    
    with col_produtos:
        st.subheader("➕ Adicionar ao Carrinho")
        
        orcamentos_salvos = listar_orcamentos()
        if orcamentos_salvos:
            # Cria a lista de opções (já está em ordem alfabética pela busca do banco)
            opcoes_pdv = {f"{o['nome_peca']} - R$ {o['preco_final']:.2f}": o for o in orcamentos_salvos}
            
            # UI/UX: O seletor vira uma barra de pesquisa inteligente!
            item_selecionado = st.selectbox(
                "🔍 Pesquise e selecione o produto:", 
                options=list(opcoes_pdv.keys()),
                index=None, # Faz começar vazio
                placeholder="Digite o nome do produto..."
            )
            
            # O cartão do produto só aparece DEPOIS que o usuário escolher algo
            if item_selecionado:
                item_dados = opcoes_pdv[item_selecionado]
                
                st.markdown("---")
                
                # UI/UX: Cartão de Produto Compacto
                col_img_card, col_detalhes_card = st.columns([1, 1.5])
                
                with col_img_card:
                    if item_dados.get('imagem_base64'):
                        try:
                            img_bytes = base64.b64decode(item_dados['imagem_base64'])
                            st.image(img_bytes, use_container_width=True)
                        except:
                            st.error("Erro na imagem")
                    else:
                        st.info("📷 Sem foto")
                        
                with col_detalhes_card:
                    st.markdown(f"**Produto:** {item_dados['nome_peca']}")
                    st.markdown(f"**Valor Unitário:** R$ {item_dados['preco_final']:.2f}")
                    
                    quantidade_item = st.number_input("Quantidade:", min_value=1, value=1, step=1)
                    
                    if st.button("Adicionar ao Carrinho", type="primary", use_container_width=True):
                        st.session_state.carrinho.append({
                            "id": item_dados['id'],
                            "nome": item_dados['nome_peca'],
                            "quantidade": quantidade_item,
                            "preco_unit": float(item_dados['preco_final']),
                            "subtotal": quantidade_item * float(item_dados['preco_final'])
                        })
                        # Ordena o carrinho alfabeticamente após adicionar
                        st.session_state.carrinho = sorted(st.session_state.carrinho, key=lambda x: x['nome'])
                        st.rerun()
        else:
            st.info("O seu catálogo está vazio. Calcule peças na aba Calculadora.")

    with col_carrinho:
        st.subheader("🛒 Orçamento Atual")
        
        if len(st.session_state.carrinho) == 0:
            st.write("Nenhum item adicionado ainda.")
        else:
            total_carrinho = 0
            for index, item in enumerate(st.session_state.carrinho):
                total_carrinho += item['subtotal']
                
                col_nome, col_qtd, col_preco, col_btn = st.columns([3, 1, 1.5, 1])
                col_nome.write(f"**{item['nome']}**")
                col_qtd.write(f"{item['quantidade']} un")
                col_preco.write(f"R\$ {item['subtotal']:.2f}")
                
                if col_btn.button("❌", key=f"remover_{index}", help="Remover item"):
                    st.session_state.carrinho.pop(index)
                    st.rerun()
            
            st.divider()
            st.markdown(f"### 💰 TOTAL GERAL: R\$ {total_carrinho:.2f}")
            
            col_pdf, col_limpar = st.columns(2)
            with col_pdf:
                pdf_gerado = criar_pdf_orcamento_multiplo(st.session_state.carrinho, total_carrinho)
                st.download_button(
                    label="📄 Baixar PDF do Orçamento",
                    data=pdf_gerado,
                    file_name="Orcamento_Impressao3D.pdf",
                    mime="application/pdf",
                    type="primary",
                    use_container_width=True
                )
            
            with col_limpar:
                if st.button("🗑️ Limpar Carrinho", use_container_width=True):
                    st.session_state.carrinho = []
                    st.rerun()

# ------------------------------------------
# ABA 3: GERENCIAR PRODUTOS (CATÁLOGO)
# ------------------------------------------
with aba_produtos:
    st.header("📦 Gerenciar Produtos")
    st.write("Edite as informações, reajuste os preços de venda ou troque a foto dos seus produtos.")
    
    orcamentos_salvos = listar_orcamentos()
    
    if orcamentos_salvos:
        opcoes_editar_prod = {f"{o['nome_peca']} - R$ {o['preco_final']:.2f}": o for o in orcamentos_salvos}
        produto_selecionado = st.selectbox(
            "Pesquise o produto que deseja editar:", 
            options=list(opcoes_editar_prod.keys()),
            index=None,
            placeholder="Digite para buscar o produto..."
        )
        
        if produto_selecionado:
            produto_dados = opcoes_editar_prod[produto_selecionado]
            id_produto = produto_dados['id']
            
            st.divider()
            
            col_img_prod, col_form_prod = st.columns([1, 2.5])
            
            with col_img_prod:
                st.write("**Foto Atual:**")
                if produto_dados.get('imagem_base64'):
                    try:
                        img_bytes = base64.b64decode(produto_dados['imagem_base64'])
                        st.image(img_bytes, use_container_width=True)
                    except:
                        st.error("Erro na imagem")
                else:
                    st.info("📷 Sem foto cadastrada.")
                    
            with col_form_prod:
                with st.form(f"form_editar_prod_{id_produto}"):
                    novo_nome = st.text_input("Descrição do Produto", value=produto_dados['nome_peca'])
                    novo_preco = st.number_input("Preço de Venda (R$)", value=float(produto_dados['preco_final']), step=1.0)
                    nova_foto = st.file_uploader("Trocar Foto (Deixe em branco para manter a atual)", type=["png", "jpg", "jpeg"])
                    
                    st.write(f"*(Custo de Produção salvo: R$ {produto_dados['custo_total']:.2f})*")
                    
                    if st.form_submit_button("💾 Salvar Alterações", type="primary"):
                        dados_update = {
                            "nome_peca": novo_nome,
                            "preco_final": novo_preco
                        }
                        
                        if nova_foto is not None:
                            img = Image.open(nova_foto)
                            if img.mode in ("RGBA", "P"): 
                                img = img.convert("RGB")
                            img.thumbnail((400, 400))
                            buffered = io.BytesIO()
                            img.save(buffered, format="JPEG", quality=85)
                            dados_update["imagem_base64"] = base64.b64encode(buffered.getvalue()).decode("utf-8")
                            
                        supabase.table("orcamentos").update(dados_update).eq("id", id_produto).execute()
                        st.success("Produto atualizado com sucesso!")
                        st.rerun()
                        
            st.divider()
            if st.button("🗑️ Excluir Produto do Banco de Dados", type="secondary"):
                supabase.table("orcamentos").delete().eq("id", id_produto).execute()
                st.toast("Produto removido permanentemente!")
                st.rerun()
            
    else:
        st.info("Seu catálogo está vazio.")

# ------------------------------------------
# ABA 4: FILAMENTOS
# ------------------------------------------
with aba_filamentos:
    st.header("Gerenciar Filamentos")
    with st.expander("➕ Adicionar Novo Filamento", expanded=False):
        with st.form("form_novo_filamento", clear_on_submit=True):
            col_mat, col_cor, col_preco = st.columns(3)
            with col_mat:
                novo_material = st.text_input("Material (ex: PLA)")
            with col_cor:
                nova_cor = st.text_input("Cor")
            with col_preco:
                novo_preco = st.number_input("Preço 1Kg (R$)", min_value=0.0, format="%.2f")
                
            if st.form_submit_button("Salvar Novo Filamento"):
                if novo_material and nova_cor:
                    supabase.table("filamentos").insert(
                        {"material": novo_material, "cor": nova_cor, "preco_por_kg": novo_preco}
                    ).execute()
                    st.success("Adicionado com sucesso!")
                    st.rerun()
                else:
                    st.error("Preencha material e cor!")

    st.divider()
    if lista_filamentos:
        st.subheader("📋 Filamentos Cadastrados")
        st.dataframe(lista_filamentos, use_container_width=True, hide_index=True)
        st.divider()
        st.subheader("✏️ Editar ou Excluir")
        opcoes_editar = {f"ID {f['id']} - {f['material']} {f['cor']}": f for f in lista_filamentos}
        filamento_selecionado = st.selectbox("Selecione o Filamento que deseja alterar:", options=list(opcoes_editar.keys()))
        filamento_dados = opcoes_editar[filamento_selecionado]
        id_selecionado = filamento_dados['id']
        
        col_edit1, col_edit2 = st.columns(2)
        with col_edit1:
            with st.form("form_editar"):
                preco_atual = float(filamento_dados['preco_por_kg'])
                novo_preco_editado = st.number_input("Atualizar preço (R$)", value=preco_atual, min_value=0.0, format="%.2f")
                if st.form_submit_button("Salvar Preço", type="primary"):
                    supabase.table("filamentos").update({"preco_por_kg": novo_preco_editado}).eq("id", id_selecionado).execute()
                    st.success("Preço atualizado!")
                    st.rerun()
                    
        with col_edit2:
            st.write(" ")
            st.write(" ")
            if st.button("🗑️ Excluir Filamento", type="secondary"):
                supabase.table("filamentos").delete().eq("id", id_selecionado).execute()
                st.error("Filamento excluído!")
                st.rerun()

# ------------------------------------------
# ABA 5: CONFIGURAÇÕES
# ------------------------------------------
with aba_configuracoes:
    st.header("Configurações do Negócio")
    config_atual = obter_configuracoes()
    
    with st.form("form_configuracoes"):
        col1, col2 = st.columns(2)
        with col1:
            novo_kwh = st.number_input("Preço do kWh (R$)", value=float(config_atual['preco_kwh']), step=0.05, format="%.2f")
            nova_potencia = st.number_input("Potência da Máquina (Watts)", value=float(config_atual['potencia_impressora_watts']), step=10.0)
            nova_taxa = st.number_input("Taxa de Falhas (%)", value=float(config_atual.get('taxa_falhas_pct', 10.0)), step=1.0)
        with col2:
            novo_valor_hora = st.number_input("Sua Hora (R$)", value=float(config_atual.get('valor_hora_operador', 30.0)), step=1.0)
            novo_desgaste = st.number_input("Desgaste/Hora (R$)", value=float(config_atual.get('custo_desgaste_por_hora', 0.5)), step=0.1)
        
        if st.form_submit_button("Atualizar Configurações"):
            novos_dados = {
                "preco_kwh": novo_kwh, 
                "potencia_impressora_watts": nova_potencia,
                "valor_hora_operador": novo_valor_hora,
                "custo_desgaste_por_hora": novo_desgaste,
                "taxa_falhas_pct": nova_taxa
            }
            supabase.table("configuracoes").update(novos_dados).eq("id", 1).execute()
            st.success("Configurações atualizadas!")
            st.rerun()
