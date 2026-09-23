// Filled in by the "pages" workflow from the repo variables SUPABASE_URL, SUPABASE_ANON_KEY, TELEGRAM_BOT.
// The anon key is public by design; row-level security in the database is what protects each user's data.
window.PW_CONFIG = {
  supabaseUrl: "",
  supabaseAnonKey: "",
  telegramBot: "",
  checkIntervalMinutes: 5,
  maxItems: 100,
  cronMinutes: [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55],   // minutes past the hour the checker runs (see check.yml)
};
