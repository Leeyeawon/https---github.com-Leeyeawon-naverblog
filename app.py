from flask import Flask, render_template, request, jsonify
import requests
import json
import sqlite3

app = Flask(__name__)

# --- ⚠️ 중요: 네이버 API 인증 정보 입력 ⚠️ ---
# 실제 값으로 대체해야 합니다!
CLIENT_ID = "0FCGPReX_yMr60Eyvava" 
CLIENT_SECRET = "E_YQ6gIqk6"
# ---------------------------------------------

# 네이버 블로그 검색 API URL
NAVER_API_URL = "https://openapi.naver.com/v1/search/blog.json"
DB_NAME = 'search_rank.db' # SQLite 데이터베이스 파일 이름

# ==========================================================
# 🔍 SQLite 데이터베이스 관리 함수
# ==========================================================

def get_db_connection():
    """데이터베이스 연결 객체를 반환합니다."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row # 컬럼 이름으로 데이터에 접근할 수 있도록 설정
    return conn

def init_db():
    """데이터베이스를 초기화(테이블 생성)합니다."""
    conn = get_db_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS keywords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT NOT NULL UNIQUE,
            count INTEGER NOT NULL DEFAULT 1
        );
        """
    )
    conn.commit()
    conn.close()

def save_search_query(query):
    """검색어를 저장하거나 횟수를 1 증가시킵니다."""
    conn = get_db_connection()
    try:
        # 1. UPDATE 실행: 커서 객체를 변수에 저장합니다.
        cursor = conn.execute(
            "UPDATE keywords SET count = count + 1 WHERE keyword = ?", (query,)
        )
        
        # 2. 커서 객체의 rowcount를 확인합니다.
        if cursor.rowcount == 0: 
            # 업데이트된 행이 없다면 (새로운 검색어라면) 삽입
            conn.execute(
                "INSERT INTO keywords (keyword) VALUES (?)", (query,)
            )
            
        conn.commit()
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    finally:
        conn.close()

def get_top_keywords(limit=10):
    """검색 횟수가 많은 상위 키워드를 가져옵니다."""
    conn = get_db_connection()
    # count 기준 내림차순 정렬하여 상위 limit개만 선택
    keywords = conn.execute(
        "SELECT keyword, count FROM keywords ORDER BY count DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return keywords

# ==========================================================
# 🌐 Flask 라우팅 설정
# ==========================================================

@app.route('/blog', methods=['GET', 'POST'])
def search_blog():
    search_results = None
    if request.method == 'POST':
        query = request.form.get('query')
        if query:
            # 1. 검색어 DB에 저장/업데이트
            save_search_query(query)

            # 1. API 요청 헤더 설정
            headers = {
                "X-Naver-Client-Id": CLIENT_ID,
                "X-Naver-Client-Secret": CLIENT_SECRET
            }
            
            # 2. API 요청 파라미터 설정
            # query: 검색어, display: 검색 결과 수 (최대 100), sort: 정렬 옵션 (sim: 정확도순, date: 날짜순)
            params = {
                "query": query, # 검색어에 "맛집"을 추가하여 블로그 검색 정확도 높이기
                "display": 20,
                "sort": "sim" 
            }

            # 3. 네이버 API 호출
            response = requests.get(NAVER_API_URL, headers=headers, params=params)
            
            if response.status_code == 200:
                data = response.json()
                search_results = data.get('items')
            else:
                # API 호출 오류 처리
                print(f"Error: {response.status_code}, {response.text}")

    # GET 요청이나 검색 결과가 없는 경우 None을 전달
    return render_template('index.html', search_results=search_results)

@app.route('/ranking')
def ranking():
    """인기 검색어 순위 페이지를 보여줍니다."""
    top_keywords = get_top_keywords(limit=10) # 상위 10개 키워드
    return render_template('ranking.html', top_keywords=top_keywords)

@app.route('/')
def hello():
    return 'Hello, World!'

with app.app_context():
    init_db()

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0',debug=True)