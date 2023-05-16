# visa_rescheduler
US VISA (ais.usvisa-info.com) appointment re-scheduler - Brasil adaptation

## Pré requisitos
- Ter um compromisso com o visto americano já agendado
- Google Chrome instalado (a ser controlado pelo script)
- Python v3 instalado (para executar o script)
- Token de API de Pushover e/ou Sendgrid (para notificações) (Ativar SENDGRID_API_KEY = True) em visa.py


## Configuração inicial
- Crie um arquivo `config.ini` com todos os detalhes necessários seguindo o `config.ini.example`
- Instale os pacotes python necessários: `pip3 install -r requirements.txt`

## Executando script
- `python3 visa.py`

## Recomendações
- Recomendo colocar o script [Heroku](https://id.heroku.com/login)
- Crie uma aplicação no heroku
- Vá em `settings` e na sessão `Config Vars`, clique em `Reveal config vars`, defina todas as variáveis do config.ini.exemple e adicione também
```
CHROMEDRIVER_PATH = /app/.chromedriver/bin/chromedriver
ENABLE_RESCHEDULE = True
```

- Agora precisamos configurar os `Buildpacks`.
Adicionar na sequência, python deve ficar no topo dos buildspacks:
```
heroku/python
https://github.com/heroku/heroku-buildpack-google-chrome
```

## Acknowledgement
Thanks to @yaojialyu for creating the initial script!

## Usos:
- O script foi melhorado para buscar em vários consulados, exemplo: SP e RJ, caso tenha data disponível
- Integração com telegram
- Configure dias para se organizar

```
; Brasila = 54 - Casv 58
; São Paulo = 56 - Casv 60
; Rio de Janeiro = 55 - Casv 59
; Recife = 57
; Porto Alegre = 128
```
