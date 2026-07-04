from database import get_db_connection

def create_users_table():

    conn = get_db_connection()

    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id VARCHAR(36) NOT NULL,
            first_name VARCHAR(50) NOT NULL,
            last_name VARCHAR(50) NOT NULL,
            email VARCHAR(100) NOT NULL,
            password VARCHAR(255) NULL,
            google_id VARCHAR(255) NULL,
            profile_picture TEXT NULL,
            role VARCHAR(20) NOT NULL DEFAULT 'user',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY uq_user_email (email),
            UNIQUE KEY uq_user_google_id (google_id)
        ) ENGINE=InnoDB;
    """)

    conn.commit()

    cursor.close()

    conn.close()

def create_recognition_history_table():

    conn = get_db_connection()

    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recognition_history (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id VARCHAR(36) NOT NULL,
            custom_name VARCHAR(255) NOT NULL DEFAULT 'Înregistrare',
            status VARCHAR(50) NOT NULL,
            artist VARCHAR(255),
            title VARCHAR(255),
            album VARCHAR(255),
            google_drive_link TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_history_users
                FOREIGN KEY (user_id)
                REFERENCES users (id)
                ON DELETE CASCADE
        ) ENGINE=InnoDB;
    """)

    try:

        cursor.execute("ALTER TABLE recognition_history ADD COLUMN custom_name VARCHAR(255) NOT NULL DEFAULT 'Înregistrare'")

    except Exception:

        pass

    try:

        cursor.execute("ALTER TABLE recognition_history ADD COLUMN status VARCHAR(50)")

    except Exception:

        pass

    conn.commit()

    cursor.close()

    conn.close()

def create_password_resets_table():

    conn = get_db_connection()

    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS password_resets (
            id INT AUTO_INCREMENT PRIMARY KEY,
            email VARCHAR(255) NOT NULL,
            otp VARCHAR(6) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at DATETIME NOT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """)

    conn.commit()

    cursor.close()

    conn.close()

def create_audio_recordings_table():

    conn = get_db_connection()

    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audio_recordings (
            id INT AUTO_INCREMENT PRIMARY KEY,
            history_id INT NULL,
            user_id VARCHAR(36) NULL,
            drive_file_id VARCHAR(255) NULL,
            user_given_name VARCHAR(255) NULL,
            status VARCHAR(50) DEFAULT 'pending',
            audio_extension VARCHAR(10) NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_recordings_history
                FOREIGN KEY (history_id)
                REFERENCES recognition_history (id)
                ON DELETE CASCADE,
            CONSTRAINT fk_recordings_users
                FOREIGN KEY (user_id)
                REFERENCES users (id)
                ON DELETE SET NULL
        ) ENGINE=InnoDB;
    """)

    conn.commit()

    cursor.close()

    conn.close()

def create_chords_cache_table():

    conn = get_db_connection()

    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chords_cache (
            id INT AUTO_INCREMENT PRIMARY KEY,
            query_text VARCHAR(150) NOT NULL,
            song_title VARCHAR(150) NOT NULL,
            artist VARCHAR(100) NOT NULL,
            chords_text TEXT NOT NULL,
            url VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_cache_query (query_text)
        ) ENGINE=InnoDB;
    """)

    conn.commit()

    cursor.close()

    conn.close()
