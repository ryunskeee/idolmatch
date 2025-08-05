// Firebase設定
const firebaseConfig = {
    apiKey: "AIzaSyCygRdCz8m-mjDKP8mU4DCyE2XJuOhey5Q",
    authDomain: "idolapp-9370a.firebaseapp.com",
    projectId: "idolapp-9370a",
};

// Firebase初期化
if (!firebase.apps.length) {
    firebase.initializeApp(firebaseConfig);
}

window.currentUser = null; // ← 修正

const auth = firebase.auth();

function signUp() {
    const email = document.getElementById('email').value;
    const password = document.getElementById('password').value;
    auth.createUserWithEmailAndPassword(email, password)
        .then(() => {
            updateStatus('登録成功！ログインしてください。');
        })
        .catch(error => updateStatus('エラー: ' + error.message));
}

function signIn() {
    const email = document.getElementById('email').value;
    const password = document.getElementById('password').value;
    auth.signInWithEmailAndPassword(email, password)
        .then(userCredential => {
            window.currentUser = userCredential.user;
            updateStatus('ログイン成功！ページ移動までお待ちください…');
            window.location.href = "/rooms";
        })
        .catch(error => updateStatus('ログインエラー: ' + error.message));
}

function signOut() {
    auth.signOut()
        .then(() => {
            window.currentUser = null;
            updateStatus('ログアウトしました');
            hideApp();
        });
}

function updateStatus(message) {
    const statusDiv = document.getElementById('status');
    if (statusDiv) statusDiv.innerText = message;
}

// ログイン状態監視（1回だけでOK）
auth.onAuthStateChanged(user => {
    window.currentUser = user;
    if (user) {
        // ここを追加
        user.getIdToken().then(idToken => {
            localStorage.setItem('idToken', idToken);
            localStorage.setItem('uid', user.uid);
        });
        showApp && showApp();
        typeof loadPosts === "function" && loadPosts();
        updateStatus('ログイン中: ' + user.email);
    } else {
        hideApp && hideApp();
        updateStatus('ログインして下さい');
        // ログアウト時は消す
        localStorage.removeItem('idToken');
        localStorage.removeItem('uid');
    }
});

function showApp() {
    const authSection = document.getElementById('auth-section');
    const appSection = document.getElementById('app-section');
    if (authSection) authSection.style.display = 'none';
    if (appSection) appSection.style.display = 'block';
}

function hideApp() {
    const authSection = document.getElementById('auth-section');
    const appSection = document.getElementById('app-section');
    if (authSection) authSection.style.display = 'block';
    if (appSection) appSection.style.display = 'none';
}

function postContent() {
    const content = document.getElementById('post-content').value.trim();
    if (!window.currentUser) {
        updateStatus('ログインしてください');
        return;
    }
    if (!content) {
        updateStatus('投稿内容を入力してください');
        return;
    }
    window.currentUser.getIdToken().then(idToken => {
        fetch('/api/posts', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                idToken: idToken,
                content: content,
                room_id: typeof roomId !== "undefined" ? roomId : null // roomIdが未定義ならnull
            })
        })
        .then(res => res.json())
        .then(data => {
            if (data.error) {
                updateStatus('投稿エラー: ' + data.error);
            } else {
                updateStatus('投稿成功！');
                document.getElementById('post-content').value = '';
                typeof loadPosts === "function" && loadPosts();
            }
        });
    });
}

function loadPosts() {
    const postsDiv = document.getElementById('posts');
    if (!postsDiv || typeof roomId === "undefined") return;

    fetch(`/api/posts?room_id=${roomId}`)
    .then(res => res.json())
    .then(posts => {
        postsDiv.innerHTML = '';
        if (posts.length === 0) {
            postsDiv.innerText = '投稿はまだありません。';
            return;
        }
        posts.forEach(post => {
            // 投稿表示エリア
            const p = document.createElement('div');
            p.className = "post-bubble d-flex align-items-center mb-2";
            p.innerHTML = `<span style="font-weight:bold;color:#ffb300;">${post.username || post.uid}</span> ${post.content}`;

            // リアクションボタンエリア
            const reactionDiv = document.createElement('div');
            reactionDiv.style.marginLeft = "auto";
            reactionDiv.style.display = "flex";
            reactionDiv.style.alignItems = "center";

            // 👍ボタン
            const likeBtn = document.createElement('button');
            likeBtn.innerText = "👍";
            likeBtn.className = "btn btn-sm btn-outline-warning";
            likeBtn.onclick = function() {
                sendReaction(post.id, "like");
            };
            reactionDiv.appendChild(likeBtn);

            // 👍数
            const likeCount = document.createElement('span');
            likeCount.innerText = post.likes || 0;
            likeCount.style.margin = "0 8px";
            reactionDiv.appendChild(likeCount);

            // ❤️ボタン
            const heartBtn = document.createElement('button');
            heartBtn.innerText = "❤️";
            heartBtn.className = "btn btn-sm btn-outline-danger";
            heartBtn.onclick = function() {
                sendReaction(post.id, "heart");
            };
            reactionDiv.appendChild(heartBtn);

            // ❤️数
            const heartCount = document.createElement('span');
            heartCount.innerText = post.hearts || 0;
            heartCount.style.margin = "0 8px";
            reactionDiv.appendChild(heartCount);

            p.appendChild(reactionDiv);
            postsDiv.appendChild(p);
        });
    });
}

// 追加：リアクション送信関数
function sendReaction(postId, type) {
    if (!window.currentUser) {
        updateStatus('ログインしてください');
        return;
    }
    window.currentUser.getIdToken().then(idToken => {
        fetch('/api/reaction', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({idToken: idToken, post_id: postId, reaction: type})
        })
        .then(res => res.json())
        .then(data => {
            if (data.result === 'ok') {
                loadPosts();
            } else {
                updateStatus(data.error || 'リアクション失敗');
            }
        });
    });
}

function resetPassword() {
    const email = document.getElementById('email').value;
    if (!email) {
        alert('メールアドレスを入力してください');
        return;
    }
    firebase.auth().sendPasswordResetEmail(email)
        .then(() => {
            alert('パスワードリセット用のメールを送信しました');
        })
        .catch(error => {
            alert('エラー: ' + error.message);
        });
}
