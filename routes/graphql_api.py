from flask import Blueprint, jsonify, request, session
from utils import get_db, login_required
from ariadne import QueryType, make_executable_schema, graphql_sync, ObjectType

graphql_bp = Blueprint('graphql_api', __name__)

type_defs = """
    type Transaction {
        id: ID!
        amount: Float!
        date: String!
        description: String
        category: String
        type: String!
    }

    type Query {
        transactions: [Transaction!]!
        hello: String!
    }
"""

query = QueryType()

@query.field("hello")
def resolve_hello(*_):
    return "Selamat datang di GraphQL Supergraph!"

@query.field("transactions")
def resolve_transactions(*_):
    user_id = session.get('user_id')
    if not user_id:
        return []
    db = get_db()
    txs = db.execute("SELECT * FROM transactions WHERE user_id = ?", (user_id,)).fetchall()
    return [dict(t) for t in txs]

schema = make_executable_schema(type_defs, query)

@graphql_bp.route("/graphql", methods=["GET"])
def graphql_playground():
    # A simple GET returns the GraphQL playground HTML, but we will just return a message
    # since we don't have the playground static files.
    return "Gunakan metode POST ke /graphql untuk menjalankan kueri."

@graphql_bp.route("/graphql", methods=["POST"])
@login_required
def graphql_server():
    data = request.get_json()
    success, result = graphql_sync(
        schema,
        data,
        context_value=request,
        debug=False
    )
    status_code = 200 if success else 400
    return jsonify(result), status_code
