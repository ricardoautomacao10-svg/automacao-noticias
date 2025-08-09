# ==============================================================================
# BLOCO 1: IMPORTAÇÕES
# ==============================================================================
import os
import io
import json
import requests
import textwrap
import numpy as np
from flask import Flask, request, jsonify
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont
import imageio

# Importações do Google
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# ==============================================================================
# BLOCO 2: CONFIGURAÇÃO INICIAL
# ==============================================================================
load_dotenv()
app = Flask(__name__)

# Configs da IA
HUGGINGFACE_TOKEN = os.getenv("HUGGINGFACE_TOKEN")
API_URL_SUMMARIZATION = "https://api-inference.huggingface.co/models/Falconsai/text_summarization"
HEADERS = {"Authorization": f"Bearer {HUGGINGFACE_TOKEN}"}

# Configs do Vídeo/Imagem
REELS_WIDTH, REELS_HEIGHT, VIDEO_DURATION, FPS = 1080, 1920, 8, 24

# Configs do Google Drive
GOOGLE_DRIVE_FOLDER_ID = os.getenv('GOOGLE_DRIVE_FOLDER_ID')
# Carrega as credenciais do Google a partir da variável de ambiente
try:
    creds_json_str = os.getenv('GOOGLE_CREDENTIALS_JSON')
    creds_info = json.loads(creds_json_str)
    GOOGLE_CREDS = Credentials.from_service_account_info(creds_info, scopes=['https://www.googleapis.com/auth/drive'])
    drive_service = build('drive', 'v3', credentials=GOOGLE_CREDS)
    print("✅ Credenciais do Google Drive carregadas com sucesso!")
except Exception as e:
    print(f"❌ ERRO GRAVE ao carregar credenciais do Google: {e}")
    drive_service = None

# Configs da API do Meta (Facebook/Instagram)
META_API_TOKEN = os.getenv('META_API_TOKEN') # Você precisará adicionar esta variável no Render
INSTAGRAM_ID = os.getenv('INSTAGRAM_ID') # E esta também

# ==============================================================================
# BLOCO 3: FUNÇÕES AUXILIARES
# ==============================================================================
def gerar_resumo_com_ia(texto_noticia):
    # ... (Esta função continua a mesma) ...
    print("🤖 Conectando com a IA da Hugging Face para gerar resumo...")
    try:
        payload = {"inputs": texto_noticia[:1024], "parameters": {"min_length": 20, "max_length": 50}}
        response = requests.post(API_URL_SUMMARIZATION, headers=HEADERS, json=payload)
        response.raise_for_status()
        resultado = response.json()
        resumo = resultado[0]['summary_text']
        print("✅ Resumo gerado pela IA com sucesso!")
        return resumo
    except Exception as e:
        print(f"❌ Erro na IA da Hugging Face: {e}")
        return None

def criar_imagem_post(url_imagem, titulo_post):
    print(f"🎨 Começando a criação da imagem do post...")
    try:
        response_img = requests.get(url_imagem, stream=True)
        response_img.raise_for_status()
        img_bytes = io.BytesIO(response_img.content)
        imagem_noticia = Image.open(img_bytes).convert("RGBA")
        
        # Cria um fundo branco quadrado para o post
        fundo = Image.new('RGBA', (1080, 1080), (255, 255, 255, 255))
        
        # Redimensiona e cola a imagem da notícia
        imagem_noticia.thumbnail((1080, 800)) # Imagem ocupa a parte de cima
        pos_x = (1080 - imagem_noticia.width) // 2
        fundo.paste(imagem_noticia, (pos_x, 0), imagem_noticia)
        
        draw = ImageDraw.Draw(fundo)
        try:
            fonte = ImageFont.truetype("arialbd.ttf", 70)
        except IOError:
            fonte = ImageFont.load_default()
        
        linhas_texto = textwrap.wrap(titulo_post, width=30)
        texto_junto = "\n".join(linhas_texto)
        
        # Escreve o texto na parte de baixo da imagem
        draw.text((540, 940), texto_junto, font=fonte, fill=(0,0,0,255), anchor="ms", align="center")
        
        # Salva a imagem final em memória para fazer upload
        buffer_saida = io.BytesIO()
        fundo.save(buffer_saida, format='PNG')
        print(f"✅ Imagem do post criada com sucesso!")
        return buffer_saida.getvalue()
    except Exception as e:
        print(f"❌ Erro ao criar imagem com Pillow: {e}")
        return None

def upload_para_google_drive(bytes_imagem, nome_arquivo):
    if not drive_service:
        print("❌ Serviço do Google Drive não está disponível.")
        return None
    
    print(f"☁️ Fazendo upload de '{nome_arquivo}' para o Google Drive...")
    try:
        media = MediaIoBaseUpload(io.BytesIO(bytes_imagem), mimetype='image/png', resumable=True)
        file_metadata = {'name': nome_arquivo, 'parents': [GOOGLE_DRIVE_FOLDER_ID]}
        
        file = drive_service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
        
        file_id = file.get('id')
        link_visualizacao = file.get('webViewLink')

        # Torna o arquivo público para que a API do Meta possa acessá-lo
        drive_service.permissions().create(fileId=file_id, body={'type': 'anyone', 'role': 'reader'}).execute()
        
        # Precisamos de um link direto para a imagem, não a página de visualização
        link_direto = f"https://drive.google.com/uc?id={file_id}"

        print(f"✅ Imagem salva no Google Drive! Link direto: {link_direto}")
        return link_direto
    except Exception as e:
        print(f"❌ Erro ao fazer upload para o Google Drive: {e}")
        return None

def publicar_no_instagram(url_imagem, legenda):
    print("📤 Publicando no Instagram...")
    try:
        # Passo 1: Criar o container de mídia
        url_container = f"https://graph.facebook.com/v18.0/{INSTAGRAM_ID}/media"
        params_container = {
            'image_url': url_imagem,
            'caption': legenda,
            'access_token': META_API_TOKEN
        }
        response_container = requests.post(url_container, params=params_container)
        response_container.raise_for_status()
        id_criacao = response_container.json()['id']
        
        # Passo 2: Publicar o container
        url_publicacao = f"https://graph.facebook.com/v18.0/{INSTAGRAM_ID}/media_publish"
        params_publicacao = {
            'creation_id': id_criacao,
            'access_token': META_API_TOKEN
        }
        response_publicacao = requests.post(url_publicacao, params=params_publicacao)
        response_publicacao.raise_for_status()
        
        print("✅ Post publicado no Instagram com sucesso!")
        return True
    except Exception as e:
        print(f"❌ Erro ao publicar no Instagram: {e}")
        return False

# ==============================================================================
# BLOCO 4: O MAESTRO (RECEPTOR DO WEBHOOK)
# ==============================================================================
@app.route('/webhook-receiver', methods=['POST'])
def webhook_receiver():
    print("\n\n🔔 Webhook recebido do WordPress!")
    dados_brutos = request.json
    dados_wp = dados_brutos[0] if isinstance(dados_brutos, list) and dados_brutos else dados_brutos
    
    try:
        url_noticia = dados_wp.get('post_permalink')
        titulo_noticia = dados_wp.get('post', {}).get('post_title')
        html_content = dados_wp.get('post', {}).get('post_content')
        if not html_content: raise ValueError("Conteúdo do post não encontrado.")
        
        soup_img = BeautifulSoup(html_content, 'html.parser')
        primeira_imagem_tag = soup_img.find('img')
        if not primeira_imagem_tag: raise ValueError("Nenhuma tag <img> encontrada.")
        
        url_imagem_destaque = primeira_imagem_tag.get('src')
        if not all([url_noticia, titulo_noticia, url_imagem_destaque]):
            raise ValueError("Dados essenciais faltando.")
    except Exception as e:
        print(f"❌ Erro ao processar dados do webhook: {e}")
        return jsonify({"status": "erro", "mensagem": "Payload do webhook com formato inválido."}), 400

    print(f"📰 Notícia recebida: {titulo_noticia}")
    
    texto_noticia = BeautifulSoup(html_content, 'html.parser').get_text(separator='\n', strip=True)
    print("✅ Texto da notícia extraído com sucesso.")

    # ORQUESTRAÇÃO FINAL
    resumo_ia = gerar_resumo_com_ia(texto_noticia)
    if not resumo_ia: return jsonify({"status": "erro", "mensagem": "Falha na IA."}), 500
    
    imagem_gerada_bytes = criar_imagem_post(url_imagem_destaque, titulo_noticia)
    if not imagem_gerada_bytes: return jsonify({"status": "erro", "mensagem": "Falha na criação da imagem."}), 500
    
    nome_do_arquivo = f"post_{dados_wp.get('post_id', 'post_sem_id')}.png"
    link_drive = upload_para_google_drive(imagem_gerada_bytes, nome_do_arquivo)
    if not link_drive: return jsonify({"status": "erro", "mensagem": "Falha no upload para o Google Drive."}), 500

    legenda_final = f"{titulo_noticia}\n\n{resumo_ia}\n\n#noticias #brasil #jornalismo"
    publicado_com_sucesso = publicar_no_instagram(link_drive, legenda_final)

    if publicado_com_sucesso:
        print("✅ Automação concluída com sucesso!")
        return jsonify({"status": "sucesso"}), 200
    else:
        return jsonify({"status": "erro", "mensagem": "Falha ao publicar no Instagram."}), 500

# ==============================================================================
# BLOCO 5: INICIALIZAÇÃO
# ==============================================================================
if __name__ == '__main__':
    print("✅ Automação iniciada!")
    app.run(host='0.0.0.0', port=5001, debug=True)