import os
import streamlit as st
from supabase import create_client, Client
from dotenv import load_dotenv

# Carrega as variáveis do arquivo .env (apenas quando rodar no seu computador)
load_dotenv()

# ==========================================
# CONFIGURAÇÃO DA PÁGINA
# ==========================================
st.set_page_config(page_title="Precificador 3D Pro", page_icon="🖨️", layout="centered")

# ==========================================
# CONEXÃO COM SUPABASE (HÍBRIDO: LOCAL E NUVEM)
# ==========================================
# Ele tenta pegar do .env (os.getenv). Se vier vazio, ele pega da nuvem (st.secrets)
try:
    SUPABASE_URL = os.getenv("SUPABASE_URL") or st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = os.getenv("SUPABASE_KEY") or st.secrets["SUPABASE_KEY"]
except KeyError:
    st.error("⚠️ Chaves do Supabase não encontradas! Verifique seu arquivo .env (local) ou os Secrets (nuvem).")
    st.stop() # Para o aplicativo para não dar erro na tela

@st.cache_resource
def init_connection():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_connection()

# ==========================================
# FUNÇÕES DE BANCO DE DADOS
# ==========================================
def listar_filamentos():
    return supabase.table("filamentos").select("*").execute().data

def obter_configuracoes():
    return supabase.table("configuracoes").select("*").eq("id", 1).execute().data[0]

# ==========================================
# INTERFACE DO USUÁRIO
# ==========================================
st.title("🖨️ Precificador 3D Profissional")

# Carregamos a lista de filamentos logo no início para usar em várias abas
lista_filamentos = listar_filamentos()

aba_calculadora, aba_filamentos, aba_configuracoes = st.tabs(["💰 Calculadora", "🧵 Filamentos", "⚙️ Configurações"])

# ------------------------------------------
# ABA 1: CALCULADORA
# ------------------------------------------
with aba_calculadora:
    st.header("Calcular Preço da Peça")
    
    if not lista_filamentos:
        st.warning("Cadastre um filamento na aba 'Filamentos' primeiro!")
    else:
        opcoes_filamentos = {f"{f['material']} {f['cor']}": f for f in lista_filamentos}
        filamento_selecionado = st.selectbox("Filamento usado:", options=list(opcoes_filamentos.keys()))
        
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
            
            # Cálculos
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
            
            # Resultados
            st.divider()
            st.subheader("📊 Detalhamento dos Custos Reais")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Material", f"R$ {custo_material:.2f}")
            m2.metric("Energia", f"R$ {custo_energia:.2f}")
            m3.metric("Custo Máquina", f"R$ {custo_desgaste:.2f}")
            m4.metric("Mão de Obra", f"R$ {custo_mao_obra:.2f}")
            
            st.info(f"**Custo Total de Produção:** R$ {custo_total:.2f}")
            st.success(f"🎯 **PREÇO FINAL SUGERIDO:** R\$ {preco_final:.2f} (Lucro: R\$ {valor_lucro:.2f})")

# ------------------------------------------
# ABA 2: FILAMENTOS (CADASTRAR, EDITAR E EXCLUIR)
# ------------------------------------------
with aba_filamentos:
    st.header("Gerenciar Filamentos")
    
    # 1. EXPANDER PARA ADICIONAR NOVO
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
    
    # 2. MOSTRAR TABELA E OPÇÕES DE EDIÇÃO/EXCLUSÃO
    if lista_filamentos:
        st.subheader("📋 Filamentos Cadastrados")
        st.dataframe(lista_filamentos, use_container_width=True, hide_index=True)
        
        st.divider()
        st.subheader("✏️ Editar ou Excluir")
        
        # Cria as opções mostrando o ID para evitar confusão de nomes repetidos
        opcoes_editar = {f"ID {f['id']} - {f['material']} {f['cor']}": f for f in lista_filamentos}
        filamento_selecionado = st.selectbox("Selecione o Filamento que deseja alterar:", options=list(opcoes_editar.keys()))
        
        filamento_dados = opcoes_editar[filamento_selecionado]
        id_selecionado = filamento_dados['id']
        
        col_edit1, col_edit2 = st.columns(2)
        
        # Formulário de Atualização
        with col_edit1:
            with st.form("form_editar"):
                st.write("**Atualizar Preço:**")
                preco_atual = float(filamento_dados['preco_por_kg'])
                novo_preco_editado = st.number_input("Novo valor (R$)", value=preco_atual, min_value=0.0, format="%.2f")
                
                if st.form_submit_button("Atualizar Preço", type="primary"):
                    supabase.table("filamentos").update({"preco_por_kg": novo_preco_editado}).eq("id", id_selecionado).execute()
                    st.success("Preço atualizado!")
                    st.rerun()
                    
        # Botão de Exclusão
        with col_edit2:
            st.write("**Remover do sistema:**")
            st.warning("Esta ação não pode ser desfeita.")
            if st.button("🗑️ Excluir Filamento", type="secondary"):
                supabase.table("filamentos").delete().eq("id", id_selecionado).execute()
                st.error("Filamento excluído!")
                st.rerun()
                
    else:
        st.info("Nenhum filamento cadastrado ainda.")

# ------------------------------------------
# ABA 3: CONFIGURAÇÕES
# ------------------------------------------
with aba_configuracoes:
    st.header("Configurações do Negócio e Máquina")
    config_atual = obter_configuracoes()
    
    with st.form("form_configuracoes"):
        st.subheader("Custos Fixos e Taxas")
        col1, col2 = st.columns(2)
        with col1:
            novo_kwh = st.number_input("Preço do kWh (R$)", value=float(config_atual['preco_kwh']), step=0.05, format="%.2f")
            nova_potencia = st.number_input("Potência da Impressora (Watts)", value=float(config_atual['potencia_impressora_watts']), step=10.0)
            nova_taxa = st.number_input("Taxa de Falhas/Suportes (%)", value=float(config_atual.get('taxa_falhas_pct', 10.0)), step=1.0)
        with col2:
            novo_valor_hora = st.number_input("Sua Hora de Trabalho (R$)", value=float(config_atual.get('valor_hora_operador', 30.0)), step=1.0)
            novo_desgaste = st.number_input("Custo de Desgaste/Hora (R$)", value=float(config_atual.get('custo_desgaste_por_hora', 0.5)), step=0.1)
        
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