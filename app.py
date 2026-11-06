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
