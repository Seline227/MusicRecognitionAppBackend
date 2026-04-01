from database import get_db_connection


def create_recognition_history_table():
    """Creates the recognition_history table if it doesn't exist."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recognition_history (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id VARCHAR(36),
            artist VARCHAR(255),
            title VARCHAR(255),
            album VARCHAR(255),
            google_drive_link TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    cursor.close()
    conn.close()


def create_password_resets_table():
    """Creates the password_resets table if it doesn't exist."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS password_resets (
            id INT AUTO_INCREMENT PRIMARY KEY,
            email VARCHAR(255) NOT NULL,
            otp VARCHAR(6) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at DATETIME NOT NULL
        )
    """)
    conn.commit()
    cursor.close()
    conn.close()
