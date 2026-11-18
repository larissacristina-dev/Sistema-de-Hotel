import os
import math
import re
from datatime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from flask import Flask, jsonify, request, send_from_directory

try:
  from mysql.connector.errors import IntegrityError
except ModuleNotFoundError:
  IntegrityError = Exception

try:
  from dotenv import load_dotenv
except ModuleNorFoundError:
  def load_dotenv ():
    return False

from database import get_connection, init_db

load_dotenv()

app = Flask(__name__, static_folder='.', static_url_path='')

try:
  init_db()
except Exception as exc:
  raise RuntimeError(f"[APP] Não foi possível inicializar o banco MySQL: {exc}") from exc


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def server_frontend(path):
  if path.startswith("api/"):
    return jsonify({"erro": "Endpoint não encontrado."}), 404

  if not path:
    return send_from_directory(app.static_folder, "index.html")

  full_path = os.path.join(app.static_folder, path)
  if os.path.isfile(full_path):
    return send_from_directory(app.static_folder, "index.html")

 return send_from_directory(app.static_folder, "index.html")


@app.route("/api")
def home():
  return jsonify({
      "message": "API do Hotel Grand Horizon",
      "status": "online"
    })

  
@app.route("/api/health")
def health():
    try:
        conn = get_connection()
        conn.close()
        return jsonify({
            "status": "ok",
            "database": os.getenv("DB_NAME", "hotel_grand_horizon"),
            "mysql": "online"
        })
    except Exception as exc:
        return jsonify({
            "status": "degraded",
            "database": os.getenv("DB_NAME", "hotel_grand_horizon"),
            "mysql": "offline",
            "message": str(exc)
        }), 503

  
    def normalize_cnpj(value):
    return re.sub(r"\D", "", str(value or ""))


def parse_discount_rate(value):
  try:
    rate = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
  except (InvalidOperation, TypeError, ValueError):
    raise ValueError("O desconto deve ser um porcentual entre 0 e 100.")
    if not rate.is_finite() or rate < 0 or rate > 100:
      raise ValueError("O desconto deve ser um porcentual entre 0 e 100.")
      return rate


@app.route("/api/convenios", methods=["GET", "POST"])
def convenios():
    if request.method == "GET":
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, razao_social, cnpj, desconto_percentual, ativo, "
            "(arquivado_em IS NOT NULL) AS arquivado "
            "FROM convenios ORDER BY razao_social"
        )
 records = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify(records)

    dados = request.get_json(force=True, silent=True) or {}
    razao_social = str(dados.get("razao_social") or "").strip()
    cnpj = normalize_cnpj(dados.get("cnpj"))
    if not razao_social or len(razao_social) > 150:
        return jsonify({"erro": "Informe a razão social (até 150 caracteres)."}), 400
    if len(cnpj) != 14:
        return jsonify({"erro": "O CNPJ deve conter 14 números."}), 400
    try:
        desconto = parse_discount_rate(dados.get("desconto_percentual"))
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO convenios (razao_social, cnpj, desconto_percentual) "
            "VALUES (%s, %s, %s)",
            (razao_social, cnpj, str(desconto)),
        )
        conn.commit()
        convenio_id = cursor.lastrowid
    except Exception as exc:
        conn.rollback()
        if getattr(exc, "errno", None) == 1062:
            return jsonify({"erro": "Já existe um convênio cadastrado com este CNPJ."}), 409
        raise
    finally:
        cursor.close()
        conn.close()

    return jsonify({
        "id": convenio_id,
        "razao_social": razao_social,
        "cnpj": cnpj,
        "desconto_percentual": float(desconto),
        "ativo": 1,
        "arquivado": False,
    }), 201


@app.route("/api/convenios/<int:convenio_id>", methods=["PATCH"])
def atualizar_convenio(convenio_id):
    dados = request.get_json(force=True, silent=True) or {}
    updates = {}
    if "razao_social" in dados:
        razao_social = str(dados["razao_social"] or "").strip()
        if not razao_social or len(razao_social) > 150:
            return jsonify({"erro": "Informe a razão social (até 150 caracteres)."}), 400
        updates["razao_social"] = razao_social
    if "cnpj" in dados:
        cnpj = normalize_cnpj(dados["cnpj"])
        if len(cnpj) != 14:
            return jsonify({"erro": "O CNPJ deve conter 14 números."}), 400
        updates["cnpj"] = cnpj
    if "desconto_percentual" in dados:
        try:
            updates["desconto_percentual"] = str(parse_discount_rate(dados["desconto_percentual"]))
        except ValueError as exc:
            return jsonify({"erro": str(exc)}), 400
    if "ativo" in dados:
        if dados["ativo"] not in (True, False, 0, 1):
            return jsonify({"erro": "O status do convênio deve ser ativo ou inativo."}), 400
        updates["ativo"] = int(bool(dados["ativo"]))
    if not updates:
        return jsonify({"erro": "Informe ao menos um campo para atualizar."}), 400

    assignments = ", ".join(f"`{column}` = %s" for column in updates)
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            f"UPDATE convenios SET {assignments} WHERE id = %s AND arquivado_em IS NULL",
            (*updates.values(), convenio_id),
        )
        if cursor.rowcount == 0:
            cursor.execute(
                "SELECT arquivado_em FROM convenios WHERE id = %s",
                (convenio_id,),
            )
            record = cursor.fetchone()
            if record is None:
                conn.rollback()
                return jsonify({"erro": "Convênio não encontrado."}), 404
            if record[0] is not None:
                conn.rollback()
                return jsonify({"erro": "Restaure o convênio antes de editá-lo."}), 409
        conn.commit()
    except Exception as exc:
        conn.rollback()
        if getattr(exc, "errno", None) == 1062:
            return jsonify({"erro": "Já existe um convênio cadastrado com este CNPJ."}), 409
        raise
    finally:
        cursor.close()
        conn.close()
    return jsonify({"message": "Convênio atualizado com sucesso.", "id": convenio_id})


@app.route("/api/convenios/<int:convenio_id>", methods=["DELETE"])
def excluir_convenio(convenio_id):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE convenios SET ativo = 0, arquivado_em = CURRENT_TIMESTAMP "
            "WHERE id = %s AND arquivado_em IS NULL",
            (convenio_id,),
        )
        if cursor.rowcount == 0:
            cursor.execute("SELECT id FROM convenios WHERE id = %s", (convenio_id,))
            if cursor.fetchone() is None:
                conn.rollback()
                return jsonify({"erro": "Convênio não encontrado."}), 404
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()
    return jsonify({"message": "Convênio arquivado com sucesso.", "id": convenio_id})


@app.route("/api/convenios/<int:convenio_id>/restaurar", methods=["POST"])
def restaurar_convenio(convenio_id):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE convenios SET ativo = 0, arquivado_em = NULL "
            "WHERE id = %s AND arquivado_em IS NOT NULL",
            (convenio_id,),
        )
        if cursor.rowcount == 0:
            cursor.execute("SELECT id FROM convenios WHERE id = %s", (convenio_id,))
            if cursor.fetchone() is None:
                conn.rollback()
                return jsonify({"erro": "Convênio não encontrado."}), 404
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()
    return jsonify({"message": "Convênio restaurado como desativado.", "id": convenio_id})


@app.route("/api/quartos", methods=["GET"]) 
def listar_quartos():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM quartos ORDER BY numero")
    quartos = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(quartos)


@app.route("/api/quartos", methods=["POST"]) 
def criar_quarto():
    dados = request.get_json(force=True, silent=True) or {}

    numero = dados.get("numero")
    tipo = dados.get("tipo")
    status = dados.get("status", "Disponível")
    preco_diaria = dados.get("preco_diaria")

    if not numero or not tipo or preco_diaria is None:
        return jsonify({"erro": "Campos numero, tipo e preco_diaria são obrigatórios."}), 400
    try:
        preco_diaria = float(preco_diaria)
        if not math.isfinite(preco_diaria) or preco_diaria <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"erro": "preco_diaria deve ser um valor maior que zero."}), 400
    if status not in {"Disponível", "Ocupado", "Em Limpeza", "Manutenção"}:
        return jsonify({"erro": "Status de quarto inválido."}), 400

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO quartos (numero, tipo, status, preco_diaria) VALUES (%s, %s, %s, %s)",
        (numero, tipo, status, preco_diaria),
    )
    conn.commit()
    quarto_id = cursor.lastrowid
    cursor.close()
    conn.close()

    return jsonify({
        "id": quarto_id,
        "numero": numero,
        "tipo": tipo,
        "status": status,
        "preco_diaria": float(preco_diaria)
    }), 201


@app.route("/api/quartos/<int:quarto_id>", methods=["PATCH"]) 
def atualizar_quarto(quarto_id):
    dados = request.get_json(force=True, silent=True) or {}
    novo_status = dados.get("status")

    if novo_status not in {"Disponível", "Ocupado", "Em Limpeza", "Manutenção"}:
        return jsonify({"erro": "Status inválido. Use Disponível, Ocupado, Em Limpeza ou Manutenção."}), 400

    conn = get_connection()
    cursor = conn.cursor()
    try:
        conn.start_transaction()
        cursor.execute("SELECT id FROM quartos WHERE id = %s FOR UPDATE", (quarto_id,))
        if cursor.fetchone() is None:
            conn.rollback()
            return jsonify({"erro": "Quarto não encontrado."}), 404
        cursor.execute(
            "SELECT id FROM check_in WHERE quarto_id = %s "
            "AND status = 'Hospedado' AND data_saida IS NULL LIMIT 1",
            (quarto_id,),
        )
        hospedagem_ativa = cursor.fetchone()
        if hospedagem_ativa and novo_status != "Ocupado":
            conn.rollback()
            return jsonify({"erro": "Finalize o check-out antes de alterar o status deste quarto."}), 409
        if not hospedagem_ativa and novo_status == "Ocupado":
            conn.rollback()
            return jsonify({"erro": "Registre o check-in para ocupar este quarto."}), 409
        cursor.execute("UPDATE quartos SET status = %s WHERE id = %s", (novo_status, quarto_id))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

    return jsonify({"message": "Status atualizado com sucesso.", "id": quarto_id, "status": novo_status})


@app.route("/api/checkin", methods=["POST"]) 
def registrar_checkin():
    dados = request.get_json(force=True, silent=True) or {}

    nome_hospede = dados.get("nome_hospede") or dados.get("nome")
    documento = dados.get("documento")
    quarto = dados.get("quarto")
    quarto_id = dados.get("quarto_id")
    tipo_documento = dados.get("tipo_documento")
    data_nascimento = dados.get("nascimento") or None
    genero = dados.get("genero") or None
    telefone = dados.get("telefone") or None
    email = dados.get("email") or None
    endereco = dados.get("endereco") or None
    empresa_parceira = dados.get("empresa_parceira") or None
    cnpj_empresa = dados.get("cnpj_empresa") or None
    preferencias = dados.get("preferencias") or None
    if not nome_hospede or not documento or (not quarto and not quarto_id):
        return jsonify({"erro": "nome_hospede, documento e quarto são obrigatórios."}), 400

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        conn.start_transaction()
        if quarto_id is None:
            cursor.execute(
                "SELECT id, numero, status FROM quartos WHERE numero = %s LIMIT 1 FOR UPDATE",
                (str(quarto),),
            )
        else:
            try:
                quarto_id = int(quarto_id)
            except (TypeError, ValueError):
                conn.rollback()
                return jsonify({"erro": "quarto_id inválido."}), 400
            cursor.execute(
                "SELECT id, numero, status FROM quartos WHERE id = %s LIMIT 1 FOR UPDATE",
                (quarto_id,),
            )
        quarto_db = cursor.fetchone()
        if quarto_db is None:
            conn.rollback()
            return jsonify({"erro": f"Quarto {quarto or quarto_id} não encontrado."}), 404

        cursor.execute(
            "SELECT id, quarto_id, nome_hospede FROM check_in "
            "WHERE documento = %s AND status = 'Hospedado' LIMIT 1",
            (documento,),
        )
        hospedagem_existente = cursor.fetchone()
        if hospedagem_existente:
            if (
                hospedagem_existente["quarto_id"] == quarto_db["id"]
                and hospedagem_existente["nome_hospede"] == nome_hospede
            ):
                conn.commit()
                checkin_id = hospedagem_existente["id"]
                return jsonify({
                    "message": "Check-in já estava registrado no banco.",
                    "id": checkin_id,
                    "nome_hospede": nome_hospede,
                    "documento": documento,
                    "quarto_id": quarto_db["id"],
                    "quarto": str(quarto_db["numero"]),
                }), 200
            conn.rollback()
            return jsonify({"erro": "Este documento já possui uma hospedagem ativa."}), 409
        if quarto_db["status"] != "Disponível":
            conn.rollback()
            return jsonify({"erro": "O quarto selecionado não está disponível."}), 409
        cursor.execute(
            "SELECT id FROM check_in WHERE quarto_id = %s AND status = 'Hospedado' LIMIT 1",
            (quarto_db["id"],),
        )
        if cursor.fetchone():
            conn.rollback()
            return jsonify({"erro": "Este quarto já possui uma hospedagem ativa."}), 409

        quarto_id = quarto_db["id"]
        cnpj_digits = normalize_cnpj(cnpj_empresa)
        convenio = None
        if len(cnpj_digits) == 14:
            cursor.execute(
                "SELECT id, razao_social, desconto_percentual FROM convenios "
                "WHERE cnpj = %s AND ativo = 1 AND arquivado_em IS NULL LIMIT 1",
                (cnpj_digits,),
            )
            convenio = cursor.fetchone()
        if convenio and not empresa_parceira:
            empresa_parceira = convenio["razao_social"]
        convenio_id = convenio["id"] if convenio else None
        desconto_percentual = convenio["desconto_percentual"] if convenio else Decimal("0.00")
        cursor.execute(
            "INSERT INTO check_in (nome_hospede, documento, quarto_id, data_saida, status, "
            "tipo_documento, data_nascimento, genero, telefone, email, endereco, "
            "empresa_parceira, cnpj_empresa, preferencias, convenio_id, desconto_percentual) "
            "VALUES (%s, %s, %s, NULL, 'Hospedado', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                nome_hospede, documento, quarto_id, tipo_documento, data_nascimento,
                genero, telefone, email, endereco, empresa_parceira, cnpj_empresa, preferencias,
                convenio_id, str(desconto_percentual),
            ),
        )
        checkin_id = cursor.lastrowid
        cursor.execute(
            "UPDATE quartos SET status = 'Ocupado' WHERE id = %s AND status = 'Disponível'",
            (quarto_id,),
        )
        if cursor.rowcount != 1:
            conn.rollback()
            return jsonify({"erro": "O quarto deixou de estar disponível. Atualize e tente novamente."}), 409
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

    return jsonify({
        "message": "Check-in realizado com sucesso.",
        "id": checkin_id,
        "nome_hospede": nome_hospede,
        "documento": documento,
        "quarto_id": quarto_id,
        "quarto": str(quarto_db["numero"]),
        "convenio": convenio["razao_social"] if convenio else None,
        "desconto_percentual": float(desconto_percentual),
    }), 201


@app.route("/api/hospedes", methods=["GET"]) 
def listar_hospedes():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT c.id, c.nome_hospede, c.documento, c.quarto_id, c.status, "
        "c.data_entrada, c.data_saida, c.tipo_documento, "
        "DATE_FORMAT(c.data_nascimento, '%Y-%m-%d') AS data_nascimento, "
        "c.genero, c.telefone, c.email, c.endereco, c.empresa_parceira, "
        "c.cnpj_empresa, c.convenio_id, c.desconto_percentual, c.preferencias, q.numero, q.tipo "
        "FROM check_in c JOIN quartos q ON q.id = c.quarto_id "
        "WHERE c.status = 'Hospedado' AND c.data_saida IS NULL "
        "ORDER BY c.data_entrada DESC"
    )
    hospedes = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(hospedes)


@app.route("/api/checkin/<int:checkin_id>", methods=["PATCH", "DELETE"])
def gerenciar_ficha_hospede(checkin_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        conn.start_transaction()
        cursor.execute(
            "SELECT id, quarto_id FROM check_in "
            "WHERE id = %s AND status = 'Hospedado' AND data_saida IS NULL "
            "LIMIT 1 FOR UPDATE",
            (checkin_id,),
        )
        ficha = cursor.fetchone()
        if ficha is None:
            conn.rollback()
            return jsonify({"erro": "Ficha ativa não encontrada."}), 404

        if request.method == "DELETE":
            cursor.execute("DELETE FROM check_in WHERE id = %s", (checkin_id,))
            if ficha["quarto_id"]:
                cursor.execute(
                    "SELECT id FROM check_in WHERE quarto_id = %s "
                    "AND status = 'Hospedado' AND data_saida IS NULL LIMIT 1",
                    (ficha["quarto_id"],),
                )
                if cursor.fetchone() is None:
                    cursor.execute(
                        "UPDATE quartos SET status = 'Disponível' "
                        "WHERE id = %s AND status = 'Ocupado'",
                        (ficha["quarto_id"],),
                    )
            conn.commit()
            return jsonify({
                "message": "Ficha excluída do banco de dados.",
                "checkin_id": checkin_id,
            })

        dados = request.get_json(force=True, silent=True) or {}
        field_map = {
            "nome_hospede": "nome_hospede",
            "documento": "documento",
            "tipo_documento": "tipo_documento",
            "nascimento": "data_nascimento",
            "genero": "genero",
            "telefone": "telefone",
            "email": "email",
            "endereco": "endereco",
            "empresa_parceira": "empresa_parceira",
            "cnpj_empresa": "cnpj_empresa",
            "preferencias": "preferencias",
        }
        updates = {}
        for request_key, column in field_map.items():
            if request_key in dados:
                value = dados[request_key]
                updates[column] = str(value).strip() if value is not None and value != "" else None
        if not updates:
            conn.rollback()
            return jsonify({"erro": "Informe ao menos um campo para atualizar."}), 400
        if "nome_hospede" in updates and not updates["nome_hospede"]:
            conn.rollback()
            return jsonify({"erro": "O nome do hóspede é obrigatório."}), 400
        if "documento" in updates and not updates["documento"]:
            conn.rollback()
            return jsonify({"erro": "O documento do hóspede é obrigatório."}), 400
        if "documento" in updates:
            cursor.execute(
                "SELECT id FROM check_in WHERE documento = %s "
                "AND status = 'Hospedado' AND data_saida IS NULL AND id <> %s LIMIT 1",
                (updates["documento"], checkin_id),
            )
            if cursor.fetchone():
                conn.rollback()
                return jsonify({"erro": "Este documento já está vinculado a outra hospedagem ativa."}), 409
        if "data_nascimento" in updates and updates["data_nascimento"]:
            try:
                date.fromisoformat(updates["data_nascimento"])
            except ValueError:
                conn.rollback()
                return jsonify({"erro": "Data de nascimento inválida."}), 400

        assignments = ", ".join(f"`{column}` = %s" for column in updates)
        cursor.execute(
            f"UPDATE check_in SET {assignments} WHERE id = %s",
            (*updates.values(), checkin_id),
        )
        conn.commit()
        return jsonify({"message": "Ficha atualizada no banco de dados.", "checkin_id": checkin_id})
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


@app.route("/api/chaves", methods=["POST"])
def solicitar_segunda_chave():
    dados = request.get_json(force=True, silent=True) or {}
    checkin_id = dados.get("checkin_id")
    if not isinstance(checkin_id, int) or isinstance(checkin_id, bool) or checkin_id <= 0:
        return jsonify({"erro": "checkin_id inválido."}), 400

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        conn.start_transaction()
        cursor.execute(
            "SELECT c.id, c.quarto_id, q.numero FROM check_in c "
            "JOIN quartos q ON q.id = c.quarto_id "
            "WHERE c.id = %s AND c.status = 'Hospedado' AND c.data_saida IS NULL "
            "LIMIT 1 FOR UPDATE",
            (checkin_id,),
        )
        ficha = cursor.fetchone()
        if ficha is None:
            conn.rollback()
            return jsonify({"erro": "Não existe hospedagem ativa para emitir outra chave."}), 404
        cursor.execute(
            "INSERT INTO solicitacoes_chaves (checkin_id, quarto_id) VALUES (%s, %s)",
            (ficha["id"], ficha["quarto_id"]),
        )
        key_request_id = cursor.lastrowid
        conn.commit()
        return jsonify({
            "message": f"Solicitação de segunda chave registrada no banco para o quarto {ficha['numero']}.",
            "id": key_request_id,
            "checkin_id": ficha["id"],
            "quarto": str(ficha["numero"]),
        }), 201
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def montar_extrato_checkout(cursor, checkin_id, lock=False):
    query = (
        "SELECT c.id, c.nome_hospede, c.documento, c.quarto_id, c.data_entrada, "
        "c.empresa_parceira, c.convenio_id, c.desconto_percentual, "
        "q.numero, q.tipo, q.preco_diaria "
        "FROM check_in c LEFT JOIN quartos q ON q.id = c.quarto_id "
        "WHERE c.id = %s AND c.status = 'Hospedado' AND c.data_saida IS NULL "
        "LIMIT 1"
    )
    cursor.execute(query + (" FOR UPDATE" if lock else ""), (checkin_id,))
    hospedagem = cursor.fetchone()
    if hospedagem is None:
        return None
    if hospedagem["quarto_id"] is None or hospedagem["preco_diaria"] is None:
        raise ValueError("A hospedagem não possui uma suíte vinculada com diária cadastrada.")

    cursor.execute(
        "SELECT GREATEST(DATEDIFF(CURDATE(), DATE(%s)), 1) AS noites",
        (hospedagem["data_entrada"],),
    )
    noites = int(cursor.fetchone()["noites"])
    cursor.execute("SELECT CURRENT_TIMESTAMP AS gerado_em")
    gerado_em = cursor.fetchone()["gerado_em"]
    cursor.execute(
        "SELECT id, nome_item, categoria, quantidade, valor_unitario, valor_total, data_hora "
        "FROM consumos WHERE quarto_id = %s AND data_hora >= %s "
        "AND data_hora <= %s ORDER BY data_hora, id",
        (hospedagem["quarto_id"], hospedagem["data_entrada"], gerado_em),
    )
    consumos_da_estadia = cursor.fetchall()

    diaria = Decimal(str(hospedagem["preco_diaria"]))
    percentual = Decimal(str(hospedagem["desconto_percentual"] or 0))
    subtotal_diarias = (diaria * noites).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    valor_desconto = (
        subtotal_diarias * percentual / Decimal("100")
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    total_consumos = sum(
        (Decimal(str(item["valor_total"])) for item in consumos_da_estadia),
        Decimal("0.00"),
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    total = (subtotal_diarias - valor_desconto + total_consumos).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    return {
        "checkin_id": hospedagem["id"],
        "nome_hospede": hospedagem["nome_hospede"],
        "documento": hospedagem["documento"],
        "quarto_id": hospedagem["quarto_id"],
        "quarto": str(hospedagem["numero"]),
        "tipo_quarto": hospedagem["tipo"],
        "data_entrada": hospedagem["data_entrada"],
        "gerado_em": gerado_em,
        "empresa_parceira": hospedagem["empresa_parceira"],
        "noites": noites,
        "valor_diaria": float(diaria),
        "subtotal_diarias": float(subtotal_diarias),
        "desconto_percentual": float(percentual),
        "valor_desconto": float(valor_desconto),
        "total_consumos": float(total_consumos),
        "total": float(total),
        "itens_consumo": [
            {
                "nome": item["nome_item"],
                "categoria": item["categoria"],
                "quantidade": item["quantidade"],
                "valor_unitario": float(item["valor_unitario"]),
                "total": float(item["valor_total"]),
                "data_hora": item["data_hora"],
            }
            for item in consumos_da_estadia
        ],
    }


@app.route("/api/checkin/<int:checkin_id>/checkout", methods=["GET", "PATCH", "POST"])
def checkout_hospede(checkin_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        if request.method == "GET":
            extrato = montar_extrato_checkout(cursor, checkin_id)
            if extrato is None:
                return jsonify({"erro": "Hospedagem ativa não encontrada."}), 404
            return jsonify(extrato)

        conn.start_transaction()
        extrato = montar_extrato_checkout(cursor, checkin_id, lock=True)
        if extrato is None:
            conn.rollback()
            return jsonify({"erro": "Check-in não encontrado ou já foi encerrado."}), 404

        cursor.execute(
            "UPDATE check_in SET status = 'Finalizado', data_saida = CURRENT_TIMESTAMP, "
            "noites_cobradas = %s, subtotal_diarias = %s, total_consumos = %s, "
            "valor_desconto = %s, total_checkout = %s "
            "WHERE id = %s AND status = 'Hospedado' AND data_saida IS NULL",
            (
                extrato["noites"],
                str(Decimal(str(extrato["subtotal_diarias"]))),
                str(Decimal(str(extrato["total_consumos"]))),
                str(Decimal(str(extrato["valor_desconto"]))),
                str(Decimal(str(extrato["total"]))),
                checkin_id,
            ),
        )
        if cursor.rowcount != 1:
            conn.rollback()
            return jsonify({"erro": "Check-in não encontrado ou já foi encerrado."}), 404

        cursor.execute(
            "SELECT data_saida FROM check_in WHERE id = %s",
            (checkin_id,),
        )
        extrato["data_saida"] = cursor.fetchone()["data_saida"]
        if extrato["quarto_id"]:
            cursor.execute(
                "SELECT id FROM check_in WHERE quarto_id = %s "
                "AND status = 'Hospedado' AND data_saida IS NULL LIMIT 1",
                (extrato["quarto_id"],),
            )
            if cursor.fetchone() is None:
                cursor.execute(
                    "UPDATE quartos SET status = 'Disponível' WHERE id = %s",
                    (extrato["quarto_id"],),
                )
        conn.commit()
    except ValueError as exc:
        conn.rollback()
        return jsonify({"erro": str(exc)}), 409
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

    return jsonify({
        **extrato,
        "message": "Check-out realizado; extrato calculado e salvo no banco de dados.",
    })


@app.route("/api/consumos", methods=["GET", "POST"]) 
def consumos():
    if request.method == "GET":
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT c.id, c.quarto_id, q.numero, c.sku, c.nome_item, c.categoria, c.quantidade, c.valor_unitario, c.valor_total, c.data_hora "
            "FROM consumos c JOIN quartos q ON q.id = c.quarto_id ORDER BY c.data_hora DESC"
        )
        registros = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify(registros)

    dados = request.get_json(force=True, silent=True) or {}
    quarto = dados.get("quarto")
    nome_item = dados.get("nome") or dados.get("nome_item")
    categoria = dados.get("categoria") or "Geral"
    quantidade = dados.get("quantidade", 1)
    valor_unitario = dados.get("preco_unitario", dados.get("valor_unitario"))
    sku = str(dados.get("sku") or "").strip()

    if not quarto or not nome_item or quantidade is None or valor_unitario is None:
        return jsonify({"erro": "quarto, nome, quantidade e preço unitário são obrigatórios."}), 400
    try:
        quantidade_decimal = Decimal(str(quantidade))
        preco_decimal = Decimal(str(valor_unitario))
        if (
            not quantidade_decimal.is_finite()
            or quantidade_decimal != quantidade_decimal.to_integral_value()
            or not preco_decimal.is_finite()
        ):
            raise ValueError
        quantidade = int(quantidade_decimal)
        valor_unitario = preco_decimal.quantize(Decimal("0.01"))
        if quantidade < 1 or quantidade > 99 or valor_unitario < 0:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"erro": "Quantidade deve ser 1–99 e o preço não pode ser negativo."}), 400
    except InvalidOperation:
        return jsonify({"erro": "Quantidade e preço devem ser valores numéricos válidos."}), 400

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        conn.start_transaction()
        cursor.execute("SELECT id FROM quartos WHERE numero = %s LIMIT 1", (str(quarto),))
        quarto_db = cursor.fetchone()
        if quarto_db is None:
            conn.rollback()
            return jsonify({"erro": f"Quarto {quarto} não encontrado."}), 404

        cursor.execute(
            "SELECT id FROM check_in WHERE quarto_id = %s "
            "AND status = 'Hospedado' AND data_saida IS NULL LIMIT 1 FOR UPDATE",
            (quarto_db["id"],),
        )
        if cursor.fetchone() is None:
            conn.rollback()
            return jsonify({"erro": "Só é possível lançar consumo para uma hospedagem ativa."}), 409

        valor_total = (Decimal(quantidade) * valor_unitario).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        cursor.execute(
            "INSERT INTO consumos (quarto_id, sku, nome_item, categoria, quantidade, valor_unitario, valor_total) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (quarto_db["id"], sku, nome_item, categoria, quantidade, str(valor_unitario), str(valor_total)),
        )
        consumo_id = cursor.lastrowid
        conn.commit()
        cursor.execute("SELECT data_hora FROM consumos WHERE id = %s", (consumo_id,))
        data_hora = cursor.fetchone()["data_hora"]
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

    return jsonify({
        "id": consumo_id,
        "quarto": quarto,
        "quarto_id": quarto_db["id"],
        "sku": sku,
        "nome": nome_item,
        "categoria": categoria,
        "quantidade": quantidade,
        "preco_unitario": float(valor_unitario),
        "total": float(valor_total),
        "created_at": data_hora.isoformat() if data_hora else None
    }), 201


if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "false").lower() == "true", host=os.getenv("FLASK_HOST", "0.0.0.0"), port=int(os.getenv("FLASK_PORT", "5000")))
