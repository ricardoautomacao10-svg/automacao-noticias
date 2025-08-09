import os
import json
from flask import Flask, request, jsonify
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

@app.route('/webhook-receiver', methods=['POST'])
def webhook_receiver():
    print("\n\n🕵️ MODO ESPIÃO ATIVADO 🕵️")
    dados_recebidos = request.json
    
    # Imprime os dados brutos que chegam do WordPress
    print("--- DADOS COMPLETOS RECEBIDOS DO WORDPRESS ---")
    print(json.dumps(dados_recebidos, indent=4)) # Usamos json.dumps para formatar e facilitar a leitura
    print("---------------------------------------------")
    
    return jsonify({"status": "dados recebidos e registrados no log."}), 200

if __name__ == '__main__':
    print("✅ Servidor espião iniciado!")
    app.run(host='0.0.0.0', port=5001, debug=True)