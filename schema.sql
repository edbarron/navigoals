-- Main Table: Tasks with assigned dates
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    daily_id INTEGER NOT NULL, -- Resettable daily ID
    name TEXT NOT NULL, -- Task name
    date DATE NOT NULL, -- Assigned date for the task
    status TEXT DEFAULT 'pending', -- Task status: 'pending', 'done', 'failed', 'moved', 'cancelled'
    category TEXT, -- Category: 'study', 'work', 'social', 'personal'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- Creation timestamp
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- Last update timestamp
    UNIQUE (daily_id, date) -- Ensures daily_id resets per day
);

-- Table: Master List (Recurring tasks)
CREATE TABLE IF NOT EXISTS master_list (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL, -- Name of the recurring task
    category TEXT, -- Category: 'study', 'work', 'social', 'personal'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP -- Creation timestamp
);

-- Table: Waiting List (Tasks without assigned dates)
CREATE TABLE IF NOT EXISTS waiting_list (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL, -- Name of the task without a defined date
    category TEXT, -- Category: 'study', 'work', 'social', 'personal'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP -- Creation timestamp
);

-- Table: Logs (Action records on tasks)
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    daily_id INTEGER, -- ID of the affected task
    date DATE NOT NULL, -- Date of the task
    action TEXT, -- Action performed: 'created', 'updated', 'moved', 'deleted'
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- Action timestamp
    FOREIGN KEY(daily_id, date) REFERENCES tasks(daily_id, date) ON DELETE CASCADE
);