from flask import Flask, render_template, request, send_file, flash, redirect, url_for
import csv
from datetime import datetime, timedelta
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import os
import io
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas

# Configuração inicial do Flask
app = Flask(__name__)
app.secret_key = 'sua_chave_secreta'

UPLOAD_FOLDER = 'uploads'
GENERATED_FOLDER = 'static/generated'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['GENERATED_FOLDER'] = GENERATED_FOLDER

# Criação dos diretórios, se não existirem
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(GENERATED_FOLDER, exist_ok=True)

# Função para ler os dados do arquivo CSV
def ler_dados_csv(caminho_arquivo):
    registros = []
    try:
        with open(caminho_arquivo, newline='', encoding='utf-8') as csvfile:
            reader = csv.reader(csvfile, delimiter=';')
            for row in reader:
                if len(row) == 4:
                    try:
                        registros.append({
                            "numero_entrada": row[0],
                            "estado": row[1],
                            "data_mensagem": datetime.strptime(row[2] + " " + row[3], "%d/%m/%Y %H:%M:%S")
                        })
                    except ValueError:
                        flash("Erro ao processar uma linha do CSV. Verifique o formato das datas.", "danger")
    except FileNotFoundError:
        flash("Arquivo CSV não encontrado.", "danger")
    except Exception as e:
        flash(f"Erro ao ler o arquivo CSV: {str(e)}", "danger")
    return registros

# Função para gerar o gráfico
def gerar_grafico(registros, numero_entrada_alvo, data_alvo_inicial, data_alvo_final, potencia_cv, custo_por_kwh):
    # Inicializa os dados para o gráfico
    soma_tempos_por_hora = {}
    hora_inicio = None

    for registro in registros:
        numero_entrada = registro["numero_entrada"]
        data_mensagem = registro["data_mensagem"]

        # Filtra os registros pelo número de entrada e intervalo de datas
        if numero_entrada == numero_entrada_alvo and data_alvo_inicial <= data_mensagem <= data_alvo_final:
            hora_do_dia = data_mensagem.hour
            estado = registro["estado"]
            if estado == "1":
                hora_inicio = data_mensagem
            elif estado == "0" and hora_inicio is not None:
                duracao = data_mensagem - hora_inicio
                soma_tempos_por_hora[hora_do_dia] = soma_tempos_por_hora.get(hora_do_dia, timedelta()) + duracao

    # Prepara os dados para o gráfico
    horas_do_dia = list(range(24))
    soma_tempos = [soma_tempos_por_hora.get(hora, timedelta()).total_seconds() / 60 for hora in horas_do_dia]

    fig, ax = plt.subplots(figsize=(10, 6))
    plt.bar(horas_do_dia, soma_tempos, color='blue')

    for i, valor in enumerate(soma_tempos):
        plt.text(horas_do_dia[i], valor, f'{int(valor)}', ha='center', va='bottom')

    plt.title(f'Tempos de Ativação da Entrada {numero_entrada_alvo} por Hora\n'
              f'Período: {data_alvo_inicial:%d/%m/%Y} - {data_alvo_final:%d/%m/%Y}')
    plt.xlabel('Hora do Dia')
    plt.ylabel('Soma dos Tempos (minutos)')
    plt.xticks(horas_do_dia, [str(hora) for hora in horas_do_dia])

    media_tempo = sum(soma_tempos) / len(soma_tempos)
    plt.axhline(media_tempo, color='red', linestyle='--')

    # Calcula informações adicionais
    total_tempo = int(sum(soma_tempos))
    rendimento = int(((total_tempo / 60) / ((data_alvo_final - data_alvo_inicial).total_seconds() / 3600)) * 100)
    potencia_watts = potencia_cv * 735.5
    energia_kwh = round((potencia_watts * total_tempo / 60) / 1000, 2)
    custo_reais = energia_kwh * custo_por_kwh

    legenda_texto = f'Disponibilidade: {int((data_alvo_final - data_alvo_inicial).total_seconds() / 3600)} Horas\n' \
                    f'Em uso: {total_tempo // 60} Horas\nRendimento: {rendimento} %\n' \
                    f'Média: {media_tempo:.2f} min\nConsumo: {energia_kwh} kWh\nCusto R$: {custo_reais:.2f}'

    plt.text(0.02, 0.02, legenda_texto, transform=plt.gca().transAxes,
             verticalalignment='bottom', bbox=dict(boxstyle='round', facecolor='wheat', alpha=1))

    plt.subplots_adjust(bottom=0.2, right=0.8)

    # Salva o gráfico como PDF
    pdf_path = os.path.join(app.config['GENERATED_FOLDER'], 'grafico.pdf')
    fig.savefig(pdf_path, format='pdf')

    # Converte o gráfico para PNG para exibição
    output = io.BytesIO()
    canvas = FigureCanvas(fig)
    canvas.print_png(output)

    plt.close(fig)
    return output, pdf_path

# Rota principal
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        try:
            csv_file = request.files.get('csv_file')
            if not csv_file:
                flash("Nenhum arquivo enviado. Por favor, envie um arquivo CSV.", "danger")
                return redirect(request.url)

            # Salva o arquivo substituindo o anterior
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'dados.csv')
            csv_file.save(filepath)

            registros = ler_dados_csv(filepath)
            if not registros:
                flash("O arquivo CSV está vazio ou inválido.", "danger")
                return redirect(request.url)

            numero_entrada_alvo = request.form['numero_entrada']
            data_alvo_inicial = datetime.strptime(request.form['data_inicial'], "%Y-%m-%d")
            data_alvo_final = datetime.strptime(request.form['data_final'], "%Y-%m-%d")
            potencia_cv = float(request.form['potencia_cv'])
            custo_por_kwh = float(request.form['custo_por_kwh'])

            _, pdf_path = gerar_grafico(registros, numero_entrada_alvo, data_alvo_inicial, data_alvo_final, potencia_cv, custo_por_kwh)

            flash("Gráfico gerado com sucesso. Você pode baixá-lo no link abaixo.", "success")
            return redirect(url_for('index'))

        except Exception as e:
            flash(f"Ocorreu um erro: {str(e)}", "danger")
            return redirect(request.url)

    return render_template('index.html')


# Rota para download do PDF
@app.route('/download_pdf')
def download_pdf():
    pdf_path = os.path.join(app.config['GENERATED_FOLDER'], 'grafico.pdf')
    if os.path.exists(pdf_path):
        return send_file(pdf_path, as_attachment=True)
    flash("Arquivo PDF não encontrado.", "danger")
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)