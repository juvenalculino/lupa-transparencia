from api_secrets import create_server_secrets


if __name__ == "__main__":
    if create_server_secrets():
        print("Chave de criptografia criada em .secrets/server.env.")
        print("Reinicie o FastAPI para carregar as credenciais.")
    else:
        print("As credenciais já existem; nenhum arquivo foi alterado.")
