from flask import Flask, render_template, request, redirect, url_for, g
import os
import sqlite3
import requests
from urllib.parse import quote
from bs4 import BeautifulSoup

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "search_rank.db")

# ✅ 네이버 API 키는 환경변수로 넣기 (코드에 하드코딩 금지)
NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID", "").strip()
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET", "").strip()


# -------------------------
# DB
# -------------------------
def get_db():
    db = getattr(g, "_db", None)
    if db is None:
        db = g._db = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db


@app.teardown_appcontext
def close_db(exception):
    db = getattr(g, "_db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DATABASE)
    cur = db.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS search_count (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        keyword TEXT UNIQUE NOT NULL,
        count INTEGER NOT NULL DEFAULT 1
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS melon_chart_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ranking INTEGER NOT NULL,
        title TEXT NOT NULL,
        artist TEXT NOT NULL,
        UNIQUE(ranking)
    )
    """)
    db.commit()
    db.close()


def increment_search_count(keyword: str):
    db = get_db()
    cur = db.cursor()
    cur.execute("UPDATE search_count SET count = count + 1 WHERE keyword = ?", (keyword,))
    if cur.rowcount == 0:
        cur.execute("INSERT INTO search_count (keyword, count) VALUES (?, 1)", (keyword,))
    db.commit()


# -------------------------
# Naver Blog Search
# -------------------------
def search_naver_blog(query: str, display: int = 10, sort: str = "sim"):
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        return {"items": [], "error": "NAVER API 키가 없습니다. 환경변수로 설정해주세요."}

    enc_query = quote(query)
    url = f"https://openapi.naver.com/v1/search/blog.json?query={enc_query}&display={display}&sort={sort}"
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    }

    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            return {"items": r.json().get("items", []), "error": None}
        return {"items": [], "error": f"네이버 API 오류: {r.status_code}"}
    except Exception as e:
        return {"items": [], "error": f"요청 실패: {e}"}


# -------------------------
# Melon chart scraping
# -------------------------
def fetch_melon_chart():
    url = "https://www.melon.com/chart/"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            return []

        soup = BeautifulSoup(r.text, "html.parser")
        chart = []

        rows = soup.select(".lst50, .lst100")
        for row in rows:
            rank_el = row.select_one(".rank")
            title_el = row.select_one(".ellipsis.rank01 a")
            artist_el = row.select_one(".ellipsis.rank02 a")

            rank = (rank_el.text.strip() if rank_el else "")
            title = (title_el.text.strip() if title_el else "제목 없음")
            artist = (artist_el.text.strip() if artist_el else "아티스트 없음")

            if rank.isdigit():
                chart.append({"rank": int(rank), "title": title, "artist": artist})

        return chart
    except Exception:
        return []


def save_melon_chart_to_db(chart_data):
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM melon_chart_data")

    for item in chart_data:
        cur.execute(
            "INSERT OR REPLACE INTO melon_chart_data (ranking, title, artist) VALUES (?, ?, ?)",
            (item["rank"], item["title"], item["artist"]),
        )
    db.commit()


def get_artist_count_ranking(limit=10):
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        SELECT artist, COUNT(*) AS song_count
        FROM melon_chart_data
        GROUP BY artist
        ORDER BY song_count DESC, artist ASC
        LIMIT ?
    """, (limit,))
    return cur.fetchall()


# -------------------------
# Routes (템플릿 파일명에 맞춤)
# -------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/blog")
def blog():
    q = (request.args.get("query") or "").strip()

    results = []
    error = None

    if q:
        increment_search_count(q)
        resp = search_naver_blog(q, display=10)
        results = resp["items"]
        error = resp["error"]

    return render_template("search_blog.html", query=q, results=results, error=error)


@app.route("/ranking")
def ranking():
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT keyword, count FROM search_count ORDER BY count DESC LIMIT 10")
    top_keywords = cur.fetchall()
    return render_template("ranking.html", top_keywords=top_keywords)


@app.route("/melon-chart")
def melon_chart():
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT ranking, title, artist FROM melon_chart_data ORDER BY ranking ASC")
    chart_list = cur.fetchall()
    return render_template("melon_chart.html", chart_list=chart_list)


@app.route("/update-chart-db")
def update_chart_db():
    data = fetch_melon_chart()
    if data:
        save_melon_chart_to_db(data)
    return redirect(url_for("melon_chart"))


@app.route("/artist-ranking")
def artist_ranking():
    top_artists = get_artist_count_ranking()
    return render_template("artist_ranking.html", top_artists=top_artists)


@app.route("/artist-search")
def artist_search():
    query = (request.args.get("artist_query") or "").strip()

    results = []
    if query:
        db = get_db()
        cur = db.cursor()
        cur.execute(
            "SELECT ranking, title, artist FROM melon_chart_data WHERE artist LIKE ? ORDER BY ranking ASC",
            (f"%{query}%",),
        )
        results = cur.fetchall()

    # ✅ 결과까지 artist_search.html 안에서 같이 보여줌
    return render_template("artist_search.html", artist_query=query, results=results)


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
