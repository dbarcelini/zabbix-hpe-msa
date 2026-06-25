# zabbix-hpe-msa
Template e script para monitoramento avançado de storages HP P2000 G3 e HPE MSA via API

# Guia de Implementação e Configuração: Monitoramento HPE MSA via API

* **Versão do Template:** 1.0.1 (2026-06-24)
* **Compatibilidade:** Zabbix 7.0+ / 7.4+
* **Base de Desenvolvimento:** Template HPE MSA for Zabbix 4.4 with SSL
* **Desenvolvido por:** Daniel Barcelini *(com o apoio do Gemini)*

---

## 1. Nota de Créditos e Histórico de Desenvolvimento

Este ecossistema de monitoramento (Template + Script) foi desenvolvido por **Daniel Barcelini** com o apoio da inteligência artificial **Gemini** para o desenvolvimento, correção e otimização tanto do template Zabbix quanto do script Python. 

A solução teve como princípio e base inicial de arquitetura o *"Template HPE MSA for Zabbix 4.4 with SSL"*. Ao longo do tempo, o projeto evoluiu significativamente de um monitoramento básico de hardware para uma ferramenta robusta em **Pure JSON API**, focada em telemetria avançada de performance (Bps, IOPS) em tempo real. Mantêm-se os créditos à engenharia inicial, cujo motor de script foi herdado e profundamente aprimorado para suportar o atual modelo de dados e estatísticas.

---

## 2. Instalação e Configuração do Script Externo (Zabbix Server / Proxy)

O Zabbix utiliza scripts externos (*External Scripts*) para centralizar a coleta. O script `zbx-hpmsa.py` deve ser implantado diretamente no servidor do Zabbix (ou no Zabbix Proxy responsável por monitorar a rede onde está o Storage).

### 2.1 Caminho de Instalação
Mova o arquivo `zbx-hpmsa.py` para o diretório padrão de scripts externos do seu ambiente. Geralmente, o caminho padrão é:
`/usr/lib/zabbix/externalscripts/`

> **Nota:** Caso seu ambiente use um caminho customizado, valide a diretiva `ExternalScripts` no arquivo de configuração do seu `zabbix_server.conf` ou `zabbix_proxy.conf`.

### 2.2 Permissões Necessárias
O script precisa de permissões de execução e deve pertencer ao usuário do Zabbix para que o processo de polling funcione corretamente, além de necessitar de um diretório de cache para gerenciar as sessões da API (SKEY).

Execute os seguintes comandos como **root** no terminal do Linux:

cd /usr/lib/zabbix/externalscripts/
chown zabbix:zabbix zbx-hpmsa.py
chmod 755 zbx-hpmsa.py

### 2.3 Inicializando o diretório de cache
O script possui um comando interno de instalação para estruturar o banco de dados SQLite de cache local (geralmente em /tmp). Execute:
sudo -u zabbix ./zbx-hpmsa.py install

### 2.4 Dependências do Python
Certifique-se de que o Python 3 e as bibliotecas requests e urllib3 estejam presentes:
pip3 install requests urllib3

### 3. Comandos Suportados e Teste Manual (Cenário Real HP P2000 G3)
Oscript zbx-hpmsa.py trabalha com subcomandos para segmentar a coleta de dados através do argumento part.

### 3.1 Partições (part) válidas:
° Estruturais/Inventário: controllers, ports, disks, volumes, enclosures, fans, power-supplies
° Telemetria/Performance: controller-statistics, host-port-statistics, volume-statistics, vdisk-statistics

### 3.2 Sintaxe Base do Script:
zbx-hpmsa.py [--ssl direct|verify] -a [VERSAO_API] -u [USUARIO] -p [SENHA] full [IP_DO_STORAGE] [PARTICAO]

### 3.3 Exemplo Técnico Real de Execução para Testes:
Para validar se o script e o Zabbix conseguirão se comunicar perfeitamente com o equipamento homologado, rode o comando abaixo simulando o usuário zabbix.
Ambiente de Teste Validado:
° Hardware: HP P2000 G3
° Firmware: Bundle Version: TS252R007 (Build Date: Fri May  8 15:40:57 MDT 2015)
° IP do Storage: 192.168.100.50
° Usuário da API: monitor
° Senha da API: S3nh4St0r4g3!
° Coleta: Estatísticas de Performance das Controladoras

sudo -u zabbix /usr/lib/zabbix/externalscripts/zbx-hpmsa.py --ssl direct -a 2 -u monitor -p "S3nh4St0r4g3!" full 192.168.100.50 controller-statistics

Retorno Esperado: Um bloco estruturado de texto em formato JSON puro contendo as métricas em tempo real de IOPS, Bytes por segundo e dados globais de leitura/escrita processados pelas controladoras A e B do HP P2000 G3.

### 4. Detalhamento do Template (Métricas, Descobertas e Regras)
### 4.1 Itens Mestre (Master Items)
O template implementa a técnica de "Itens Mestre" para mitigar gargalos e evitar múltiplas conexões concorrentes no Storage. O Zabbix faz uma única chamada na API por minuto para cada categoria de dados, traz o JSON completo, e os demais itens (Dependentes) filtram as informações localmente via JSONPATH.

Os Itens Mestre coletados ativamente são:
° HPE MSA: Master Coletor das Controladoras (Traz saúde e IOPS estrutural)
° HPE MSA: Master Coletor das Portas (Traz status de link físico)
° HPE MSA: Master Coletor dos Discos (Traz integridade física dos HDs/SSDs)
° HPE MSA: Master Coletor de Volumes (Traz mapeamento de volumes)
° HPE MSA: Master Coletor de Enclosures (Traz saúde das gavetas)
° HPE MSA: Master Coletor de Fans / Ventoinhas (Traz saúde das ventoinhas)
° HPE MSA: Master Coletor de Fontes / Power Supplies (Traz saúde da energia)
° HPE MSA: Master Coletor - Estatisticas das Controladoras (Performance)
° HPE MSA: Master Coletor - Estatisticas de Portas (Performance de tráfego)
° HPE MSA: Master Coletor - Estatisticas de Volumes (Performance granular)
° HPE MSA: Master Coletor - Estatisticas de VDisks (Performance de arrays de discos)

4.2 Itens Criados por Descoberta Automática (LLD)
O template detecta dinamicamente os componentes físicos e lógicos existentes no P2000 G3.
° Descoberta de Controladoras:
  ° Controladora {#CONTROLLER.ID}: Carga de CPU (%)
  ° Controladora {#CONTROLLER.ID}: Taxa de IOPS
  ° Controladora {#CONTROLLER.ID}: Status de Saude (Código numérico)
° Descoberta de Performance - Controladoras:
  ° Controladora {#CTRL.ID}: IOPS Atual (Momento)
  ° Controladora {#CTRL.ID}: Soma total da banda utilizada (Momento em Bps)
  ° Controladora {#CTRL.ID}: Taxa de Dados Lidos/Gravados por Segundo
° Descoberta de Performance - Portas iSCSI/FC Ativas:
  ° Porta {#PORT.ID}: IOPS Atual (Momento)
  ° Porta {#PORT.ID}: Soma total da banda utilizada (Bps)
  ° Porta {#PORT.ID}: Taxa de Leitura/Escrita por Segundo
° Descoberta de Performance - Volumes Reais:
  ° Volume {#VOL.NAME}: IOPS, Banda Utilizada, Taxas de Leitura e Escrita
° Descoberta de Performance - VDisks:
  ° VDisk {#VDISK.NAME}: IOPS, Banda Utilizada e Latências de Leitura/Escrita (ms)
°Descoberta de Portas, Discos, Gavetas, Ventoinhas e Fontes:
  ° Itens individuais que monitoram a Saúde/Status de link de cada componente achado.
  
  ### 4.3 Triggers (Gatilhos de Alertas)
  ° Falha Crítica na Comunicação com a API: Disparada se o script não coletar dados por 5 minutos.
  ° Uso Excessivo de CPU na Controladora: Disparada se a média de CPU passar de 85% por 15 minutos.
  ° Alerta de Saúde na Controladora / Discos / Fontes / Ventoinhas: Disparada imediatamente se o status divergir do esperado.
  ° Saturação de Porta Física Gigabit: Disparada em nível de AVISO se o tráfego de uma porta monitorada ultrapassar ~85% da capacidade real de 1 Gbps (ou seja, > 106.250.000 Bps).
  
  ### 4.4 Gráficos Customizados Gerados Automaticamente
  ° Gráfico de Uso de CPU por Controladora (Eixo fixado em 0-100%).
  ° Visão Macro de Performance da Controladora (Cruza IOPS com vazão de dados em Bytes).
  ° Estatística de Uso e Escoamento de Portas (Essencial para achar gargalos na rede SAN).
  ° Volume IOPS e Vazão de Dados (Mapeia qual servidor/volume está gerando estresse).
  ° VDisk Performance Geral do Array (Entrega a visão combinada do conjunto de discos).
  
  ### 5. Configuração de Macros no Zabbix
  Ao associar o template ao Host do Storage no Zabbix, as seguintes Macros devem ser revisadas e preenchidas na aba "Macros -> Macros Herdados e do Template":

    | Macro              | Valor Padrão | Descrição / Opções de Preenchimento |
    | :---               |     :---     | :---                                |   
    | `{$API.VER}`       |     `2`      | Versão da API do Storage (Padrão: 2). |
    | `{$MSA.USERNAME}`  |   `monitor`  | Usuário criado no Storage com privilégios de leitura (Zabbix/Monitor). |
    | `{$MSA.PASSWORD}`  |   `******`   | Senha do usuário. Definida como Texto Secreto (oculta). |
    | `{$HISTORY}`       |    `7d`      | Tempo de retenção do histórico dos dados coletados. |
    | `{$TRENDS}`        |    `365d`    | Tempo de retenção das médias de longo prazo (Gráficos anuais). |
    | `{$LLD_INTERVAL}`  |    `1h`      | Frequência com que o Zabbix buscará por novos discos/componentes. |
    | `{$NODATA_RANGE}`  |    `5m`      | Tempo limite sem dados para disparar alerta de indisponibilidade. |
  
 ### 6. Manual de Operação: Interpretação dos Dados e Cultura do "Zero"
 ### 6.1 Compreendendo o Valor "0" (Zero) como Sinal de Saúde Perfeita
 Para simplificar gatilhos e visões de relatórios, a arquitetura do Storage mapeia valores textuais de status para números inteiros no Zabbix através do script.
 Desta forma, na documentação do monitoramento fica estabelecido que:
 ° STATUS OK / HEALTHY / UP / OPERACIONAL = 0 (Zero)
 Se você consultar itens como "Status de Saúde da Controladora", "Saúde do Disco Físico", "Status da Fonte" ou "Status da Ventoinha" e o gráfico reportar 0, o hardware está em perfeito estado de funcionamento. Valores maiores que 0 significam degradação (Ex: 1 para Degradado, 2 para Falha Crítica).
 
 ### 6.2 Como Analisar os Limites e o Consumo do Hardware (Capacidade)
 A análise proativa deve ser baseada no cruzamento de três pilares:
  A) Vazão de Banda (Bps) vs Limites de Infraestrutura: Se o gráfico de uma "Porta" apontar picos constantes de 100 MB/s a 115 MB/s em interfaces iSCSI de 1 Gbps, a porta está operando no limite físico máximo do cabo. A trigger de saturação alertará isso. A solução será balancear o multipath ou migrar para conexões de 10 Gbps ou Fibre Channel.
  B) IOPS vs Latência (VDisk Response Time): Discos rígidos mecânicos possuem limites severos de IOPS. Ao analisar os gráficos, se o gráfico de IOPS de um Volume/VDisk estiver muito alto e, simultaneamente, o item "Latência Total Instantânea (resp_time)" do VDisk subir para valores acima de 20ms ou 30ms, os discos físicos entraram em gargalo de escrita/leitura (Fila de E/S). Isso impacta diretamente a performance dos sistemas ou VMs hospedadas.
  C) Carga de CPU das Controladoras: A CPU do Storage gerencia o cache, desduplicação, rotas e processamento de IO. Se a CPU de uma das controladoras apresentar picos repetidos acima de 85%, significa que o hardware está operando próximo ao limite de processamento de instruções, o que pode indicar a necessidade de redistribuir os volumes preferenciais entre as controladoras A e B para equilibrar a carga de trabalho de forma homogênea.
