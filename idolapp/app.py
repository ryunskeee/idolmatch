from flask import Flask, render_template, request, jsonify, redirect, url_for
import sqlite3
import firebase_admin
from firebase_admin import credentials, auth
import os
from werkzeug.utils import secure_filename
import datetime
from dotenv import load_dotenv

app = Flask(__name__)

# 画像アップロード設定
UPLOAD_FOLDER = 'static/icons'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# 環境変数からFirebaseの認証情報を取得
load_dotenv()
cred_path = os.getenv("FIREBASE_CREDENTIAL_PATH")
cred = credentials.Certificate(cred_path)
firebase_admin.initialize_app(cred)

# DB初期化
def init_db():
    conn = sqlite3.connect("idolapp.db")
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            uid TEXT PRIMARY KEY,
            username TEXT,
            icon_url TEXT,
            profile TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS rooms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_id INTEGER,
            uid TEXT,
            content TEXT,
            FOREIGN KEY(room_id) REFERENCES rooms(id)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS match_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            img_url TEXT,
            caption TEXT,
            xAccount TEXT,
            uid TEXT,
            feature TEXT,
            idolName TEXT,
            likes INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

# 既存DBにカラム追加（初回のみ実行される）
def alter_users_table():
    conn = sqlite3.connect("idolapp.db")
    c = conn.cursor()
    try:
        c.execute("ALTER TABLE users ADD COLUMN icon_url TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("ALTER TABLE users ADD COLUMN profile TEXT")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()

def alter_posts_table():
    conn = sqlite3.connect("idolapp.db")
    c = conn.cursor()
    try:
        c.execute("ALTER TABLE posts ADD COLUMN likes INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # 既に存在する場合は無視

    try:
        c.execute("ALTER TABLE posts ADD COLUMN hearts INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # 既に存在する場合は無視

    conn.commit()
    conn.close()

init_db()
alter_users_table()
alter_posts_table()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def verify_token(id_token):
    try:
        decoded_token = auth.verify_id_token(id_token)
        uid = decoded_token['uid']
        return {'uid': uid}
    except Exception:
        return None

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/username')
def username():
    return render_template('username.html')

@app.route('/rooms')
def rooms():
    return render_template('rooms.html')

@app.route('/room/<int:room_id>')
def room(room_id):
    conn = sqlite3.connect("idolapp.db")
    c = conn.cursor()
    c.execute("SELECT name FROM rooms WHERE id = ?", (room_id,))
    row = c.fetchone()
    conn.close()
    room_name = row[0] if row else "不明な部屋"
    return render_template('room.html', room_id=room_id, room_name=room_name)

@app.route('/profile')
def profile_page():
    # プロフィール閲覧ページを表示
    return render_template('profile.html')

@app.route('/profilemake')
def profile_make_page():
    # プロフィール編集ページ（旧profile.html）を表示
    return render_template('profilemake.html')

@app.route('/terms')
def terms():
    return render_template('terms.html')


@app.route('/terms_confirm')
def terms_confirm():
    return render_template('terms_confirm.html')

@app.route('/agree_terms')
def agree_terms():
    # ここでユーザーの同意フラグをDBに保存するなどの処理を追加できます
    # 例: セッションやDBで「同意済み」フラグをセット
    return redirect('/rooms')

@app.route('/api/username', methods=['POST'])
def api_username():
    data = request.get_json()
    id_token = data.get('idToken')
    username = data.get('username')
    user = verify_token(id_token)
    if not user:
        return jsonify({'error': '認証エラー'}), 401
    uid = user['uid']
    conn = sqlite3.connect("idolapp.db")
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users (uid, username) VALUES (?, ?)", (uid, username))
    conn.commit()
    conn.close()
    return jsonify({'result': 'ok'})

@app.route('/api/username_check', methods=['POST'])
def api_username_check():
    data = request.get_json()
    uid = data.get('uid')
    conn = sqlite3.connect("idolapp.db")
    c = conn.cursor()
    c.execute("SELECT username FROM users WHERE uid = ?", (uid,))
    row = c.fetchone()
    conn.close()
    return jsonify({'need_username': not bool(row and row[0])})

@app.route('/api/rooms', methods=['GET', 'POST'])
def api_rooms():
    conn = sqlite3.connect("idolapp.db")
    c = conn.cursor()

    if request.method == 'GET':
        c.execute("SELECT id, name FROM rooms")
        rooms = [{'id': row[0], 'name': row[1]} for row in c.fetchall()]
        conn.close()
        return jsonify(rooms)

    data = request.get_json()
    name = data.get('name')
    creator_uid = data.get('creator_uid')  # 追加
    if not name or not creator_uid:
        conn.close()
        return jsonify({'error': '部屋名と作成者が必要です'}), 400
    try:
        c.execute("INSERT INTO rooms (name, creator_uid) VALUES (?, ?)", (name, creator_uid))
        conn.commit()
        new_id = c.lastrowid
        conn.close()
        return jsonify({'id': new_id, 'name': name})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': '同じ名前の部屋が既に存在します'}), 400

@app.route('/api/posts', methods=['GET', 'POST'])
def api_posts():
    conn = sqlite3.connect("idolapp.db")
    c = conn.cursor()

    if request.method == 'GET':
        room_id = request.args.get('room_id')
        if not room_id:
            conn.close()
            return jsonify([])
        # 部屋作成者のuidを取得
        c.execute("SELECT creator_uid FROM rooms WHERE id = ?", (room_id,))
        room_row = c.fetchone()
        creator_uid = room_row[0] if room_row else None

        c.execute("""
            SELECT posts.uid, users.username, users.icon_url, posts.content
            FROM posts
            LEFT JOIN users ON posts.uid = users.uid
            WHERE posts.room_id = ?
            ORDER BY posts.id DESC
        """, (room_id,))
        posts = [
            {
                'uid': row[0],
                'username': row[1],
                'icon_url': row[2],
                'content': row[3],
                'creator_uid': creator_uid  # 追加
            } for row in c.fetchall()
        ]
        conn.close()
        return jsonify(posts)

    data = request.get_json()
    id_token = data.get('idToken')
    content = data.get('content')
    room_id = data.get('room_id')
    if not (id_token and content and room_id):
        conn.close()
        return jsonify({'error': 'idToken, content, room_idが必要です'}), 400

    user = verify_token(id_token)
    if not user:
        conn.close()
        return jsonify({'error': '認証失敗'}), 401

    c.execute("INSERT INTO posts (room_id, uid, content) VALUES (?, ?, ?)",
              (room_id, user['uid'], content))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# プロフィール画像アップロードAPI
@app.route('/api/upload_icon', methods=['POST'])
def upload_icon():
    id_token = request.form.get('idToken')
    user = verify_token(id_token)
    if not user:
        return jsonify({'error': '認証エラー'}), 401
    if 'icon' not in request.files:
        return jsonify({'error': 'ファイルがありません'}), 400
    file = request.files['icon']
    if file.filename == '':
        return jsonify({'error': 'ファイル名がありません'}), 400
    if file and allowed_file(file.filename):
        filename = secure_filename(user['uid'] + '_' + file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        icon_url = url_for('static', filename='icons/' + filename)
        # DBに保存
        conn = sqlite3.connect("idolapp.db")
        c = conn.cursor()
        c.execute("UPDATE users SET icon_url = ? WHERE uid = ?", (icon_url, user['uid']))
        conn.commit()
        conn.close()
        return jsonify({'icon_url': icon_url})
    else:
        return jsonify({'error': '許可されていないファイル形式です'}), 400

# プロフィール取得API（GET）
@app.route('/api/profile', methods=['GET'])
def api_profile_get():
    id_token = request.headers.get('Authorization', '').replace('Bearer ', '')
    user = verify_token(id_token)
    if not user:
        return jsonify({'error': '認証エラー'}), 401

    uid = user['uid']
    conn = sqlite3.connect("idolapp.db")
    c = conn.cursor()
    c.execute("SELECT icon_url, username, point, profile FROM users WHERE uid=?", (uid,))
    row = c.fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'ユーザー情報がありません'}), 404

    return jsonify({
        'icon_url': row[0],
        'username': row[1],
        'point': row[2],
        'profile': row[3]
    })

# プロフィール更新API（POST）
@app.route('/api/profile', methods=['POST'])
def api_profile_post():
    data = request.get_json()
    id_token = data.get('idToken')
    profile = data.get('profile')
    username = data.get('username')
    user = verify_token(id_token)
    if not user:
        return jsonify({'error': '認証エラー'}), 401
    uid = user['uid']
    conn = sqlite3.connect("idolapp.db")
    c = conn.cursor()
    if username is not None:
        c.execute("UPDATE users SET profile = ?, username = ? WHERE uid = ?", (profile, username, uid))
    else:
        c.execute("UPDATE users SET profile = ? WHERE uid = ?", (profile, uid))
    conn.commit()
    conn.close()
    return jsonify({'result': 'ok'})



@app.route('/api/profile')
def api_profile():
    id_token = request.headers.get('Authorization', '').replace('Bearer ', '')
    user = verify_token(id_token)  # あなたの認証関数
    if not user:
        return jsonify({'error': '認証エラー'}), 401

    uid = user['uid']
    conn = sqlite3.connect("idolapp.db")
    c = conn.cursor()
    c.execute("SELECT icon_url, username, point, bio FROM users WHERE uid=?", (uid,))
    row = c.fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'ユーザー情報がありません'}), 404

    return jsonify({
        'icon_url': row[0],
        'username': row[1],
        'point': row[2],
        'bio': row[3]
    })

@app.route('/api/rooms/<int:room_id>', methods=['DELETE'])
def delete_room(room_id):
    data = request.get_json()
    id_token = data.get('idToken')
    user = verify_token(id_token)
    if not user:
        return jsonify({'error': '認証エラー'}), 401
    uid = user['uid']
    conn = sqlite3.connect("idolapp.db")
    c = conn.cursor()
    # 部屋の作成者か確認
    c.execute("SELECT creator_uid FROM rooms WHERE id = ?", (room_id,))
    row = c.fetchone()
    if not row or row[0] != uid:
        conn.close()
        return jsonify({'error': '削除権限がありません'}), 403
    # 部屋と関連投稿を削除
    c.execute("DELETE FROM posts WHERE room_id = ?", (room_id,))
    c.execute("DELETE FROM rooms WHERE id = ?", (room_id,))
    conn.commit()
    conn.close()
    return jsonify({'result': 'ok'})

@app.route('/champion')
def mission():
    return render_template('champion.html')


@app.route('/api/champion_image', methods=['GET', 'POST'])
def champion_image():
    if request.method == 'GET':
        # 画像一覧を返す（1枚だけの場合は最新1件だけ返すなど）
        files = os.listdir('static/champion_images')
        urls = [url_for('static', filename=f'champion_images/{f}') for f in files if f.lower().endswith(('.png','.jpg','.jpeg','.gif'))]
        return jsonify(urls)
    else:
        id_token = request.form.get('idToken')
        user = verify_token(id_token)
        if not user:
            return jsonify({'error': '認証エラー'}), 401

        uid = user['uid']

        # 今週のランキング1位のuidを取得
        conn = sqlite3.connect("idolapp.db")
        c = conn.cursor()
        # 例：今週の開始日を計算
        today = datetime.date.today()
        week_start = today - datetime.timedelta(days=today.weekday())
        c.execute("""
            SELECT uid FROM users
            ORDER BY level DESC, point DESC
            LIMIT 1
        """)
        row = c.fetchone()
        conn.close()
        if not row or row[0] != uid:
            return jsonify({'error': '今週のランキング1位のみアップロードできます'}), 403

        file = request.files.get('image')
        if not file:
            return jsonify({'error': '画像がありません'}), 400
        filename = secure_filename(file.filename)
        save_dir = os.path.join('static', 'champion_images')
        os.makedirs(save_dir, exist_ok=True)
        save_path = os.path.join(save_dir, filename)
        file.save(save_path)
        url = url_for('static', filename=f'champion_images/{filename}')
        return jsonify({'url': url})

@app.route('/landing')
def landing():
    return render_template('landing.html')

@app.route('/api/reaction', methods=['POST'])
def reaction():
    data = request.json
    post_id = data.get('post_id')
    reaction = data.get('reaction')
    if not post_id or not reaction:
        return jsonify({'error': 'パラメータが足りません'}), 400

    conn = sqlite3.connect("idolapp.db")
    c = conn.cursor()
    if reaction == "like":
        c.execute('UPDATE posts SET likes = COALESCE(likes,0)+1 WHERE id=?', (post_id,))
    elif reaction == "heart":
        c.execute('UPDATE posts SET hearts = COALESCE(hearts,0)+1 WHERE id=?', (post_id,))
    else:
        conn.close()
        return jsonify({'error': '不明なリアクションです'}), 400

    conn.commit()
    conn.close()
    return jsonify({'result': 'ok'})

@app.route('/api/match_idols')
def api_match_idols():
    feature = request.args.get('feature', '').strip()
    conn = sqlite3.connect("idolapp.db")
    c = conn.cursor()
    if feature:
        search_tag = feature.replace('＃', '#').replace(' ', '')
        search_tag = search_tag.strip('#')
        c.execute("""
            SELECT m.img_url, m.caption, m.id, u.username, m.xAccount, m.idolName, m.likes
            FROM match_posts m
            LEFT JOIN users u ON m.uid = u.uid
            WHERE m.feature LIKE ?
            ORDER BY m.id DESC
        """, (f'%#{search_tag}#%',))
    else:
        c.execute("""
            SELECT m.img_url, m.caption, m.id, u.username, m.xAccount, m.idolName, m.likes
            FROM match_posts m
            LEFT JOIN users u ON m.uid = u.uid
            ORDER BY m.id DESC
        """)
    idols = [
        {
            "img_url": row[0],
            "caption": row[1],
            "id": row[2],
            "username": row[3],
            "xAccount": row[4],
            "idolName": row[5],
            "likes": row[6] if row[6] is not None else 0
        }
        for row in c.fetchall()
    ]
    conn.close()
    return jsonify(idols)

@app.route('/match')
def match():
    return render_template('match.html')


@app.route('/match_post')
def match_post_page():
    return render_template('match_post.html')

@app.route('/api/match_post', methods=['POST'])
def match_post():
    id_token = request.form.get('idToken')
    caption = request.form.get('caption')
    xAccount = request.form.get('xAccount')
    feature = request.form.get('feature')
    file = request.files.get('image')
    user = verify_token(id_token)
    if not user:
        return jsonify({'error': '認証エラー'}), 401
    uid = user['uid']
    if not file:
        return jsonify({'error': '画像がありません'}), 400
    filename = secure_filename(file.filename)
    save_dir = os.path.join('static', 'match_images')
    os.makedirs(save_dir, exist_ok=True)
    save_path = os.path.join(save_dir, filename)
    file.save(save_path)
    img_url = url_for('static', filename=f'match_images/{filename}')
    # #で区切られていなければ自動で#で囲む（両端#付きにする）
    if feature:
        feature = feature.replace('＃', '#').replace(' ', '')
        tags = [t for t in feature.split('#') if t.strip()]
        if tags:
            feature = '#' + '#'.join(tags) + '#'
        else:
            feature = ''
    conn = sqlite3.connect("idolapp.db")
    c = conn.cursor()
    idolName = request.form.get('idolName', '').strip()
    c.execute(
        "INSERT INTO match_posts (img_url, caption, xAccount, uid, feature, idolName, likes) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (img_url, caption, xAccount, uid, feature, idolName, 0)
    )
    conn.commit()
    conn.close()
    return jsonify({'result': 'ok'})

@app.route('/match_tag_select')
def match_tag_select():
    return render_template('match_tag_select.html')

@app.route('/api/delete_match_post', methods=['POST'])
def delete_match_post():
    id_token = request.form.get('idToken')
    post_id = request.form.get('post_id')
    user = verify_token(id_token)
    if not user:
        return jsonify({'error': '認証エラー'}), 401
    uid = user['uid']
    conn = sqlite3.connect("idolapp.db")
    c = conn.cursor()
    # 自分の投稿だけ削除できるように
    c.execute("DELETE FROM match_posts WHERE id=? AND uid=?", (post_id, uid))
    conn.commit()
    conn.close()
    return jsonify({'result': 'ok'})

@app.route('/my_match_posts')
def my_match_posts():
    return render_template('my_match_posts.html')

@app.route('/api/my_match_posts', methods=['POST'])
def api_my_match_posts():
    data = request.get_json()
    id_token = data.get('idToken')
    user = verify_token(id_token)
    if not user:
        return jsonify([]), 401
    uid = user['uid']
    conn = sqlite3.connect("idolapp.db")
    c = conn.cursor()
    # idolNameも取得、likesも取得
    c.execute("SELECT id, img_url, caption, xAccount, feature, idolName, likes FROM match_posts WHERE uid=? ORDER BY id DESC", (uid,))
    posts = [
        {
            "id": row[0],
            "img_url": row[1],
            "caption": row[2],
            "xAccount": row[3],
            "feature": row[4],
            "idolName": row[5],
            "likes": row[6] if row[6] is not None else 0
        }
        for row in c.fetchall()
    ]
    conn.close()
    return jsonify(posts)

@app.route('/api/delete_all_my_match_posts', methods=['POST'])
def delete_all_my_match_posts():
    id_token = request.form.get('idToken')
    user = verify_token(id_token)
    if not user:
        return jsonify({'error': '認証エラー'}), 401
    uid = user['uid']
    conn = sqlite3.connect("idolapp.db")
    c = conn.cursor()
    c.execute("DELETE FROM match_posts WHERE uid=?", (uid,))
    conn.commit()
    conn.close()
    return jsonify({'result': 'ok'})

@app.route('/api/delete_all_match_posts', methods=['POST'])
def delete_all_match_posts():
    # 必要なら管理者認証を追加してください
    conn = sqlite3.connect("idolapp.db")
    c = conn.cursor()
    c.execute("DELETE FROM match_posts")
    conn.commit()
    conn.close()
    return jsonify({'result': 'ok'})

@app.route('/api/like_match_post', methods=['POST'])
def like_match_post():
    data = request.get_json()
    post_id = data.get('post_id')
    id_token = data.get('idToken')
    user = verify_token(id_token)
    if not user:
        return jsonify({'result': 'error', 'error': '認証エラー'}), 401
    uid = user['uid']

    conn = sqlite3.connect("idolapp.db")
    c = conn.cursor()
    # すでにいいねしているか確認
    c.execute("SELECT 1 FROM match_post_likes WHERE post_id=? AND user_uid=?", (post_id, uid))
    if c.fetchone():
        conn.close()
        return jsonify({'result': 'error', 'error': 'すでにいいねしています'})
    # いいね記録＆カウント加算
    c.execute("INSERT INTO match_post_likes (post_id, user_uid) VALUES (?, ?)", (post_id, uid))
    c.execute("UPDATE match_posts SET likes = COALESCE(likes, 0) + 1 WHERE id = ?", (post_id,))
    conn.commit()
    conn.close()
    return jsonify({'result': 'ok'})

if __name__ == '__main__':
    app.run(debug=True)
