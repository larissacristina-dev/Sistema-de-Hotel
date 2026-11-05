# Hotel Grand Horizon

Projeto acadêmico de hotelaria com site institucional e sistema operacional
construído em HTML, CSS, JavaScript, Python/Flask e MySQL.

O sistema inclui painel, check-in e checkout, gestão de quartos, consumos e
convênios. Os dados operacionais são servidos pela API Flask e armazenados no
MySQL.

## Executar localmente

1. Instale Python 3 e MySQL Server.
2. Copie `.env.example` para `.env` e configure as credenciais do MySQL local.
3. Na pasta do projeto, instale os requisitos:

   ```powershell
   py -m pip install -r requirements.txt
   ```

4. Inicie o servidor:

   ```powershell
   py app.py
   ```

5. Abra <http://127.0.0.1:5000/>.

Consulte [LEIA-ME.txt](LEIA-ME.txt) para detalhes de configuração, inicialização
do banco e uso em uma rede local.

## Restaurar o backup do banco em outro computador

O backup MySQL não fica armazenado neste repositório. Primeiro, crie-o no
computador que contém os dados e transfira o arquivo `.sql` de forma segura.

### Criar o backup no computador de origem

1. Abra o MySQL Workbench e conecte-se ao servidor MySQL que contém os dados.
2. No menu, selecione **Server > Data Export**.
3. Marque o schema `hotel_grand_horizon` e selecione **Export to Self-Contained
   File**. Escolha um local seguro para salvar o arquivo `.sql`.
4. Se disponível, marque **Include Create Schema** para que o arquivo também
   contenha a criação do schema. Se essa opção não estiver marcada, crie o
   schema manualmente no destino antes da importação.
5. Selecione **Dump Structure and Data** e clique em **Start Export**.
6. Copie o backup para o computador de destino por um meio confiável. O backup
   pode conter dados pessoais de hóspedes: não o publique no GitHub.

### Importar no computador de destino

1. Instale e inicie o MySQL Server e o MySQL Workbench no computador de destino.
2. No Workbench, conecte-se ao servidor MySQL de destino. Para evitar conflitos
   ou duplicar registros, prefira importar para um schema vazio.
3. Se o backup não contiver a opção **Include Create Schema**, abra uma aba SQL
   e execute:

   ```sql
   CREATE DATABASE hotel_grand_horizon
     CHARACTER SET utf8mb4
     COLLATE utf8mb4_unicode_ci;
   ```

4. Selecione **Server > Data Import** e escolha **Import from Self-Contained
   File**. Localize o arquivo `.sql`.
5. Em **Default Target Schema**, selecione `hotel_grand_horizon`. Se o arquivo
   contiver `CREATE DATABASE`/`USE` para outro nome, ajuste para
   `hotel_grand_horizon` ou gere novamente o backup com o schema correto.
6. Clique em **Start Import** e aguarde a conclusão. Confira a área de saída
   para confirmar que a importação terminou sem erros e que as tabelas foram
   criadas.
7. Crie o `.env` local a partir de `.env.example`. Configure o acesso ao MySQL
   desse computador, mantendo `DB_NAME=hotel_grand_horizon`. O usuário MySQL
   precisa ter permissões para criar/alterar as tabelas e ler/gravar os dados.
8. Instale as dependências e inicie o sistema:

   ```powershell
   py -m pip install -r requirements.txt
   py app.py
   ```

9. Abra <http://127.0.0.1:5000/api/health>. A resposta deve indicar `"status":
   "ok"` e `"mysql": "online"`. Em seguida, acesse
   <http://127.0.0.1:5000/> e confira os quartos e registros importados.

**Importante:** faça backup antes de substituir qualquer banco. Não importe
sobre uma base operacional sem confirmar o destino, pois tabelas e dados
existentes podem entrar em conflito. Depois de importar um backup com quartos,
não execute `py seed_demo_data.py`: esse script é para preparar dados de
demonstração e pode criar hóspedes ativos. O arquivo `.env` e o backup `.sql`
contêm informações sensíveis; não os envie ao GitHub.

Se a intenção for que vários computadores trabalhem sempre com os mesmos dados,
não é necessário importar o banco em cada máquina. Mantenha Flask e MySQL
rodando em um computador servidor e acesse esse servidor nos demais navegadores.
Veja o passo a passo de rede local no [LEIA-ME.txt](LEIA-ME.txt).

## Segurança

Não publique o arquivo `.env`, backups ou dados reais de hóspedes. O sistema
atual não possui autenticação de usuários e não usa HTTPS; mantenha-o em uma
rede privada confiável. As melhorias planejadas estão descritas no LEIA-ME.
