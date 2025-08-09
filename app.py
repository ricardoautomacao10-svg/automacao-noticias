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
import google.generativeai as genai
from PIL import Image, ImageDraw, ImageFont
import imageio

# ==============================================================================
# BLOCO 2: CONFIGURAÇÃO INICIAL
# ==============================================================================
load_dotenv()
app = Flask(__name__)

try:
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
except Exception as e:
    print(f"❌ ERRO GRAVE: Não foi possível configurar a API do Gemini. Verifique sua chave no arquivo .env. Erro: {e}")

REELS_WIDTH, REELS_HEIGHT, VIDEO_DURATION, FPS = 1080, 1920, 8, 24

# ==============================================================================
# BLOCO 3: FUNÇÕES AUXILIARES (NENHUMA MUDANÇA AQUI)
# ==============================================================================
def gerar_conteudo_com_ia(texto_noticia):
    print("🤖 Conectando com a IA para gerar conteúdo...")
    try:
        model = genai.GenerativeModel('gemini-1.5-pro-latest')
        prompt = f"""
        Aja como um editor de social media para um portal de notícias brasileiro.
        Baseado na notícia abaixo, gere o seguinte conteúdo para um Reels do Instagram no formato JSON:
        1.  "titulo_video": Um título muito curto e impactante para aparecer no vídeo (máximo 10 palavras).
        2.  "legenda": Uma legenda para o post, resumindo a notícia em 2-3 frases e terminando com "Leia a matéria completa no link da bio.".
        3.  "hashtags": Uma string única contendo de 5 a 7 hashtags relevantes separadas por espaço (ex: "#noticia #brasil #politica").
        Notícia: {texto_noticia[:4000]}
        """
        response = model.generate_content(prompt)
        json_response_text = response.text.replace("```json", "").replace("```", "").strip()
        conteudo_gerado = json.loads(json_response_text)
        print("✅ Conteúdo gerado pela IA com sucesso!")
        return conteudo_gerado
    except Exception as e:
        print(f"❌ Erro na IA: {e}")
        return None

def criar_video_com_pillow(url_imagem, titulo_video, nome_arquivo_saida="reels_gerado.mp4"):
    print(f"🎬 Começando a criação do vídeo com o novo método (Pillow + Imageio)...")
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
            print("⚠️ Fonte Arial Bold não encontrada, usando fonte padrão.")
            fonte = ImageFont.load_default()
        
        linhas_texto = textwrap.wrap(titulo_video.upper(), width=20)
        texto_junto = "\n".join(linhas_texto)
        x, y = REELS_WIDTH / 2, REELS_HEIGHT * 0.8
        draw.text((x+5, y+5), texto_junto, font=fonte, fill=(0,0,0,255), anchor="ms", align="center")
        draw.text((x, y), texto_junto, font=fonte, fill=(255,255,255,255), anchor="ms", align="center")
        
        frame_final = np.array(fundo)
        frames = [frame_final for _ in range(FPS * VIDEO_DURATION)]
        
        imageio.mimsave(nome_arquivo_saida, frames, fps=FPS, codec='libx264')
        
        print(f"✅ Vídeo '{nome_arquivo_saida}' salvo com sucesso com o novo método!")
        return nome_arquivo_saida
    except Exception as e:
        print(f"❌ Erro ao criar vídeo com Pillow/Imageio: {e}")
        return None

# ==============================================================================
# BLOCO 4: O MAESTRO (RECEPTOR DO WEBHOOK) - COM AS CORREÇÕES
# ==============================================================================
@app.route('/webhook-receiver', methods=['POST'])
def webhook_receiver():
    print("\n\n🔔 Webhook recebido do WordPress!")
    dados_brutos = request.json

    if isinstance(dados_brutos, list) and dados_brutos:
        dados_wp = dados_brutos[0]
    else:
        dados_wp = dados_brutos
    
    try:
        # --- CORREÇÃO 1: PEGANDO O LINK DO LUGAR CERTO ---
        url_noticia = dados_wp.get('post_permalink')
        titulo_noticia = dados_wp.get('post', {}).get('post_title')
        
        # --- CORREÇÃO 2: EXTRAINDO A IMAGEM DE DENTRO DO CONTEÚDO ---
        html_content = dados_wp.get('post', {}).get('post_content')
        if not html_content:
            raise ValueError("Conteúdo do post não encontrado no webhook.")
        
        soup_img = BeautifulSoup(html_content, 'html.parser')
        primeira_imagem_tag = soup_img.find('img')
        
        if not primeira_imagem_tag:
             raise ValueError("Nenhuma tag <img> encontrada no conteúdo do post.")
        
        url_imagem_destaque = primeira_imagem_tag.get('src')
        
        if not all([url_noticia, titulo_noticia, url_imagem_destaque]):
            raise ValueError(f"Dados essenciais faltando. URL: {url_noticia}, Titulo: {titulo_noticia}, Imagem: {url_imagem_destaque}")

    except Exception as e:
        print(f"❌ Erro ao processar dados do webhook: {e}")
        return jsonify({"status": "erro", "mensagem": "Payload do webhook com formato inesperado ou dados faltando."}), 400

    print(f"📰 Notícia recebida: {titulo_noticia}")
    print(f"🖼️ Imagem encontrada: {url_imagem_destaque}")

    try:
        print(f"💻 Lendo o conteúdo de: {url_noticia}")
        response_page = requests.get(url_noticia)
        soup = BeautifulSoup(response_page.content, 'html.parser')
        corpo_artigo = soup.find('div', class_='entry-content') 
        texto_noticia = corpo_artigo.get_text(separator='\n', strip=True)
        print("✅ Texto da notícia extraído com sucesso.")
    except Exception as e:
        print(f"❌ Erro ao ler a página da notícia: {e}")
        return jsonify({"status": "erro", "mensagem": "Não foi possível ler a URL."}), 400

    conteudo_ia = gerar_conteudo_com_ia(texto_noticia)
    if not conteudo_ia:
        return jsonify({"status": "erro", "mensagem": "Falha na IA."}), 500
    
    caminho_video_final = criar_video_com_pillow(url_imagem_destaque, conteudo_ia['titulo_video'])
    if not caminho_video_final:
        return jsonify({"status": "erro", "mensagem": "Falha na criação do vídeo."}), 500

    legenda_final = f"{conteudo_ia['legenda']}\n.\n.\n.\n{conteudo_ia['hashtags']}"
    print("📤 Simulando publicação do Reel...")
    print(f"   -> Legenda do post: {legenda_final}")
    print("✅ Automação concluída com sucesso para esta notícia!")
    return jsonify({"status": "sucesso"}), 200

# ==============================================================================
# BLOCO 5: INICIALIZAÇÃO
# ==============================================================================
if __name__ == '__main__':
    print("✅ Automação iniciada!")
    app.run(host='0.0.0.0', port=5001, debug=True)