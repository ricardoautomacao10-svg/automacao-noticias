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

# ==============================================================================
# BLOCO 2: CONFIGURAÇÃO INICIAL
# ==============================================================================
load_dotenv()
app = Flask(__name__)

# Pega o token da Hugging Face do ambiente
HUGGINGFACE_TOKEN = os.getenv("HUGGINGFACE_TOKEN")
API_URL_SUMMARIZATION = "https://api-inference.huggingface.co/models/Falconsai/text_summarization"
HEADERS = {"Authorization": f"Bearer {HUGGINGFACE_TOKEN}"}

REELS_WIDTH, REELS_HEIGHT, VIDEO_DURATION, FPS = 1080, 1920, 8, 24

# ==============================================================================
# BLOCO 3: FUNÇÕES AUXILIARES
# ==============================================================================
def gerar_conteudo_com_ia(texto_noticia):
    print("🤖 Conectando com a IA da Hugging Face para gerar resumo...")
    try:
        # Prepara os dados para enviar para a API
        payload = {
            "inputs": texto_noticia[:1024], # Usa os primeiros 1024 caracteres
            "parameters": {"min_length": 20, "max_length": 50}
        }
        # Faz a chamada para a API
        response = requests.post(API_URL_SUMMARIZATION, headers=HEADERS, json=payload)
        response.raise_for_status() # Garante que não houve erro de API
        
        # Pega o resumo gerado
        resultado = response.json()
        resumo = resultado[0]['summary_text']
        
        print("✅ Resumo gerado pela IA com sucesso!")
        return {"legenda": resumo}
        
    except Exception as e:
        print(f"❌ Erro na IA da Hugging Face: {e}")
        return None

def criar_video_com_pillow(url_imagem, titulo_video, nome_arquivo_saida="reels_gerado.mp4"):
    # ... (Esta função continua exatamente a mesma) ...
    print(f"🎬 Começando a criação do vídeo...")
    try:
        response_img = requests.get(url_imagem, stream=True)
        response_img.raise_for_status()
        img_bytes = io.BytesIO(response_img.content)
        imagem_noticia = Image.open(img_bytes).convert("RGBA")
        
        fundo = Image.new('RGBA', (REELS_WIDTH, REELS_HEIGHT), (0, 0, 0, 255))
        imagem_noticia.thumbnail((REELS_WIDTH * 0.9, REELS_HEIGHT * 0.9))
        pos_x = (REELS_WIDTH - imagem_noticia.width) // 2
        pos_y = (REELS_HEIGHT - imagem_noticia.height) // 2
        fundo.paste(imagem_noticia, (pos_x, pos_y), imagem_noticia)
        
        draw = ImageDraw.Draw(fundo)
        try:
            fonte = ImageFont.truetype("arialbd.ttf", 90)
        except IOError:
            fonte = ImageFont.load_default()
        
        linhas_texto = textwrap.wrap(titulo_video.upper(), width=20)
        texto_junto = "\n".join(linhas_texto)
        x, y = REELS_WIDTH / 2, REELS_HEIGHT * 0.8
        draw.text((x+5, y+5), texto_junto, font=fonte, fill=(0,0,0,255), anchor="ms", align="center")
        draw.text((x, y), texto_junto, font=fonte, fill=(255,255,255,255), anchor="ms", align="center")
        
        frame_final = np.array(fundo)
        frames = [frame_final for _ in range(FPS * VIDEO_DURATION)]
        
        imageio.mimsave(nome_arquivo_saida, frames, fps=FPS, codec='libx264')
        
        print(f"✅ Vídeo '{nome_arquivo_saida}' salvo com sucesso!")
        return nome_arquivo_saida
    except Exception as e:
        print(f"❌ Erro ao criar vídeo: {e}")
        return None

# ==============================================================================
# BLOCO 4: O MAESTRO (RECEPTOR DO WEBHOOK)
# ==============================================================================
@app.route('/webhook-receiver', methods=['POST'])
def webhook_receiver():
    # ... (Esta função continua quase a mesma, só muda como usa o resultado da IA) ...
    print("\n\n🔔 Webhook recebido do WordPress!")
    dados_brutos = request.json

    if isinstance(dados_brutos, list) and dados_brutos:
        dados_wp = dados_brutos[0]
    else:
        dados_wp = dados_brutos
    
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
    print(f"🖼️ Imagem encontrada: {url_imagem_destaque}")

    try:
        print(f"💻 Lendo o conteúdo de: {url_noticia}")
        response_page = requests.get(url_noticia)
        soup = BeautifulSoup(response_page.content, 'html.parser')
        corpo_artigo = soup.find('div', class_='entry-content') or soup.find('article') or soup.find('main')
        texto_noticia = corpo_artigo.get_text(separator='\n', strip=True)
        print("✅ Texto da notícia extraído com sucesso.")
    except Exception as e:
        print(f"❌ Erro ao ler a página da notícia: {e}")
        return jsonify({"status": "erro", "mensagem": "Não foi possível ler a URL."}), 400

    conteudo_ia = gerar_conteudo_com_ia(texto_noticia)
    if not conteudo_ia:
        return jsonify({"status": "erro", "mensagem": "Falha na IA."}), 500
    
    # Usa o título original da matéria para o vídeo
    caminho_video_final = criar_video_com_pillow(url_imagem_destaque, titulo_noticia)
    if not caminho_video_final:
        return jsonify({"status": "erro", "mensagem": "Falha na criação do vídeo."}), 500

    # Usa o resumo gerado pela IA como legenda
    legenda_final = f"{conteudo_ia['legenda']}\n.\n.\n.\n#noticias #brasil"
    print("📤 Simulando publicação do Reel...")
    print(f"   -> Legenda do post: {legenda_final}")
    print("✅ Automação concluída com sucesso!")
    return jsonify({"status": "sucesso"}), 200

# ==============================================================================
# BLOCO 5: INICIALIZAÇÃO
# ==============================================================================
if __name__ == '__main__':
    print("✅ Automação iniciada com IA da Hugging Face!")
    app.run(host='0.0.0.0', port=5001, debug=True)