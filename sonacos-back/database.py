import sqlite3
import os
import hashlib
import secrets

DB_PATH = os.path.join(os.path.dirname(__file__), "vigilos.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            email       TEXT    UNIQUE NOT NULL,
            password    TEXT    NOT NULL,
            role        TEXT    NOT NULL DEFAULT 'admin_site',
            site        TEXT,
            created_at  TEXT    DEFAULT (datetime('now'))
        )
    """)

    conn.commit()

    # Créer le super admin par défaut si la table est vide
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]

    if count == 0:
        superadmin_email    = os.getenv("ADMIN_EMAIL", "superadmin@sonacos.sn")
        superadmin_password = os.getenv("ADMIN_PASSWORD", "motdepassefort")
        hashed = hash_password(superadmin_password)
        cursor.execute(
            "INSERT INTO users (email, password, role, site) VALUES (?, ?, ?, ?)",
            (superadmin_email, hashed, "superadmin", None)
        )
        conn.commit()
        print(f"✅ Super admin créé : {superadmin_email}")

    conn.close()


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(password: str, hashed: str) -> bool:
    return hash_password(password) == hashed


def get_user_by_email(email: str):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()
    return dict(user) if user else None


def get_all_users():
    conn = get_db()
    users = conn.execute("SELECT id, email, role, site, created_at FROM users").fetchall()
    conn.close()
    return [dict(u) for u in users]


def create_user(email: str, password: str, role: str, site: str = None):
    conn = get_db()
    hashed = hash_password(password)
    try:
        conn.execute(
            "INSERT INTO users (email, password, role, site) VALUES (?, ?, ?, ?)",
            (email, hashed, role, site)
        )
        conn.commit()
        return True, "Utilisateur créé avec succès"
    except sqlite3.IntegrityError:
        return False, "Cet email existe déjà"
    finally:
        conn.close()


def update_user(user_id: int, email: str = None, password: str = None, role: str = None, site: str = None):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        conn.close()
        return False, "Utilisateur introuvable"

    new_email    = email    or user["email"]
    new_role     = role     or user["role"]
    new_site     = site     if site is not None else user["site"]
    new_password = hash_password(password) if password else user["password"]

    try:
        conn.execute(
            "UPDATE users SET email=?, password=?, role=?, site=? WHERE id=?",
            (new_email, new_password, new_role, new_site, user_id)
        )
        conn.commit()
        return True, "Utilisateur mis à jour"
    except sqlite3.IntegrityError:
        return False, "Cet email existe déjà"
    finally:
        conn.close()


def delete_user(user_id: int):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        conn.close()
        return False, "Utilisateur introuvable"
    if dict(user)["role"] == "superadmin":
        conn.close()
        return False, "Impossible de supprimer le super admin"
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    return True, "Utilisateur supprimé"