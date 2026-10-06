# ============================================================
# ПОЛНЫЙ КОД ДЛЯ ИНТЕГРАЦИИ ПАРСЕРА API-FOOTBALL В БОТА
# Вставить ПЕРЕД секцией "КЛАВИАТУРЫ"
# ============================================================

import aiohttp
from datetime import datetime, timedelta

API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY", "")
API_FOOTBALL_URL = "https://v3.football.api-sports.io/fixtures"

# --- Маппинг приоритетов ---
LEAGUE_PRIORITY_MAP = {
    # P1 — сборные
    "World Cup - Qualification Europe": 1,
    "World Cup - Qualification South America": 1,
    "World Cup - Qualification Asia": 1,
    "World Cup - Qualification Africa": 1,
    "World Cup - Qualification CONCACAF": 1,
    "World Cup - Qualification Oceania": 1,
    "World Cup": 1,
    "Euro Championship": 1,
    "Euro Championship Qualification": 1,
    "UEFA Nations League": 1,

    # P2 — еврокубки
    "UEFA Champions League": 2,
    "UEFA Europa League": 2,
    "UEFA Europa Conference League": 2,
    "UEFA Super Cup": 2,
    "UEFA Champions League Qualification": 2,
    "UEFA Europa League Qualification": 2,

    # P3 — топ-лиги (8 стран)
    "Premier League": 3,
    "La Liga": 3,
    "Serie A": 3,
    "Bundesliga": 3,
    "Ligue 1": 3,
    "Eredivisie": 3,
    "Premier League (Russia)": 3,
    "Premier Liga": 3,
    "Primeira Liga": 3,

    # P4 — остальные страны (топ-лиги)
    "Pro League": 4,
    "First Division A": 4,
    "First Professional League": 4,
    "A PFG": 4,
    "Superliga": 4,
    "Super League": 4,
    "S\u00fcper Lig": 4,
    "Super Lig": 4,
    "Premier Division": 4,
    "Major League Soccer": 4,
    "Serie A - Brazil": 4,
    "Serie A (Brazil)": 4,
    "Primera Divisi\u00f3n": 4,
    "Primera Division": 4,
    "Czech First League": 4,
    "First League (Czech Republic)": 4,
    "Super League (Greece)": 4,
    "Super League 1": 4,
    "Eliteserien": 4,
    "Ekstraklasa": 4,
    "Allsvenskan": 4,
    "HNL": 4,
    "Super Liga": 4,
    "NB I": 4,
    "Bundesliga (Austria)": 4,
    "Premier League (Belarus)": 4,
    "Liga I": 4,
    "Super Liga (Slovakia)": 4,
    "PrvaLiga": 4,
    "Premier League (Ukraine)": 4,
    "Premier Liha": 4,
    "First League (Montenegro)": 4,
    "Prva CFL": 4,

    # P5 — вторые дивизионы
    "Championship": 5,
    "EFL Championship": 5,
    "Segunda Divisi\u00f3n": 5,
    "Segunda Division": 5,
    "Serie B": 5,
    "2. Bundesliga": 5,
    "First League (Russia)": 5,
    "FNL": 5,
}

COUNTRY_RU_MAP = {
    "England": "\u0410\u043d\u0433\u043b\u0438\u044f",
    "Spain": "\u0418\u0441\u043f\u0430\u043d\u0438\u044f",
    "Italy": "\u0418\u0442\u0430\u043b\u0438\u044f",
    "Germany": "\u0413\u0435\u0440\u043c\u0430\u043d\u0438\u044f",
    "France": "\u0424\u0440\u0430\u043d\u0446\u0438\u044f",
    "Netherlands": "\u041d\u0438\u0434\u0435\u0440\u043b\u0430\u043d\u0434\u044b",
    "Russia": "\u0420\u043e\u0441\u0441\u0438\u044f",
    "Portugal": "\u041f\u043e\u0440\u0442\u0443\u0433\u0430\u043b\u0438\u044f",
    "Belgium": "\u0411\u0435\u043b\u044c\u0433\u0438\u044f",
    "Bulgaria": "\u0411\u043e\u043b\u0433\u0430\u0440\u0438\u044f",
    "Denmark": "\u0414\u0430\u043d\u0438\u044f",
    "Switzerland": "\u0428\u0432\u0435\u0439\u0446\u0430\u0440\u0438\u044f",
    "Turkey": "\u0422\u0443\u0440\u0446\u0438\u044f",
    "Ireland": "\u0418\u0440\u043b\u0430\u043d\u0434\u0438\u044f",
    "Ireland Republic": "\u0418\u0440\u043b\u0430\u043d\u0434\u0438\u044f",
    "USA": "\u0421\u0428\u0410",
    "Brazil": "\u0411\u0440\u0430\u0437\u0438\u043b\u0438\u044f",
    "Argentina": "\u0410\u0440\u0433\u0435\u043d\u0442\u0438\u043d\u0430",
    "Czech Republic": "\u0427\u0435\u0445\u0438\u044f",
    "Czechia": "\u0427\u0435\u0445\u0438\u044f",
    "Greece": "\u0413\u0440\u0435\u0446\u0438\u044f",
    "Norway": "\u041d\u043e\u0440\u0432\u0435\u0433\u0438\u044f",
    "Poland": "\u041f\u043e\u043b\u044c\u0448\u0430",
    "Sweden": "\u0428\u0432\u0435\u0446\u0438\u044f",
    "Croatia": "\u0425\u043e\u0440\u0432\u0430\u0442\u0438\u044f",
    "Serbia": "\u0421\u0435\u0440\u0431\u0438\u044f",
    "Hungary": "\u0412\u0435\u043d\u0433\u0440\u0438\u044f",
    "Austria": "\u0410\u0432\u0441\u0442\u0440\u0438\u044f",
    "Belarus": "\u0411\u0435\u043b\u0430\u0440\u0443\u0441\u044c",
    "Romania": "\u0420\u0443\u043c\u044b\u043d\u0438\u044f",
    "Slovakia": "\u0421\u043b\u043e\u0432\u0430\u043a\u0438\u044f",
    "Slovenia": "\u0421\u043b\u043e\u0432\u0435\u043d\u0438\u044f",
    "Ukraine": "\u0423\u043a\u0440\u0430\u0438\u043d\u0430",
    "Montenegro": "\u0427\u0435\u0440\u043d\u043e\u0433\u043e\u0440\u0438\u044f",
    "World": "\u041c\u0438\u0440",
    "Europe": "\u0415\u0432\u0440\u043e\u043f\u0430",
}

LEAGUE_RU_MAP = {
    "World Cup": "\u0427\u0435\u043c\u043f\u0438\u043e\u043d\u0430\u0442 \u041c\u0438\u0440\u0430",
    "World Cup - Qualification Europe": "\u0427\u041c. \u041e\u0442\u0431\u043e\u0440 (\u0415\u0432\u0440\u043e\u043f\u0430)",
    "World Cup - Qualification South America": "\u0427\u041c. \u041e\u0442\u0431\u043e\u0440 (\u042e\u0436.\u0410\u043c\u0435\u0440\u0438\u043a\u0430)",
    "Euro Championship": "\u0427\u0435\u043c\u043f\u0438\u043e\u043d\u0430\u0442 \u0415\u0432\u0440\u043e\u043f\u044b",
    "Euro Championship Qualification": "\u0427\u0415. \u041e\u0442\u0431\u043e\u0440",
    "UEFA Nations League": "\u041b\u0438\u0433\u0430 \u041d\u0430\u0446\u0438\u0439",
    "UEFA Champions League": "\u041b\u0438\u0433\u0430 \u0427\u0435\u043c\u043f\u0438\u043e\u043d\u043e\u0432",
    "UEFA Europa League": "\u041b\u0438\u0433\u0430 \u0415\u0432\u0440\u043e\u043f\u044b",
    "UEFA Europa Conference League": "\u041b\u0438\u0433\u0430 \u041a\u043e\u043d\u0444\u0435\u0440\u0435\u043d\u0446\u0438\u0439",
    "UEFA Super Cup": "\u0421\u0443\u043f\u0435\u0440\u043a\u0443\u0431\u043e\u043a \u0423\u0415\u0424\u0410",
    "Premier League": "\u0410\u041f\u041b",
    "La Liga": "\u041b\u0430 \u041b\u0438\u0433\u0430",
    "Serie A": "\u0421\u0435\u0440\u0438\u044f \u0410",
    "Bundesliga": "\u0411\u0443\u043d\u0434\u0435\u0441\u043b\u0438\u0433\u0430",
    "Ligue 1": "\u041b\u0438\u0433\u0430 1",
    "Eredivisie": "\u042d\u0440\u0435\u0434\u0438\u0432\u0438\u0437\u0438",
    "Premier League (Russia)": "\u0420\u041f\u041b",
    "Premier Liga": "\u0420\u041f\u041b",
    "Primeira Liga": "\u041f\u0440\u0438\u043c\u0435\u0439\u0440\u0430",
    "Pro League": "\u041b\u0438\u0433\u0430 \u0416\u044e\u043f\u0438\u043b\u0435",
    "First Division A": "\u041b\u0438\u0433\u0430 \u0416\u044e\u043f\u0438\u043b\u0435",
    "First Professional League": "\u0411\u043e\u043b\u0433\u0430\u0440\u0438\u044f. \u041b\u0438\u0433\u0430",
    "A PFG": "\u0411\u043e\u043b\u0433\u0430\u0440\u0438\u044f. \u041b\u0438\u0433\u0430",
    "Superliga": "\u0414\u0430\u043d\u0438\u044f. \u0421\u0443\u043f\u0435\u0440\u043b\u0438\u0433\u0430",
    "Super League": "\u0428\u0432\u0435\u0439\u0446\u0430\u0440\u0438\u044f. \u0421\u0443\u043f\u0435\u0440\u043b\u0438\u0433\u0430",
    "Super Lig": "\u0422\u0443\u0440\u0446\u0438\u044f. \u0421\u0443\u043f\u0435\u0440\u043b\u0438\u0433\u0430",
    "Premier Division": "\u0418\u0440\u043b\u0430\u043d\u0434\u0438\u044f. \u041f\u0440\u0435\u043c\u044c\u0435\u0440",
    "Major League Soccer": "MLS",
    "Serie A - Brazil": "\u0411\u0440\u0430\u0437\u0438\u043b\u0438\u044f. \u0421\u0435\u0440\u0438\u044f \u0410",
    "Serie A (Brazil)": "\u0411\u0440\u0430\u0437\u0438\u043b\u0438\u044f. \u0421\u0435\u0440\u0438\u044f \u0410",
    "Primera Divisi\u00f3n": "\u0410\u0440\u0433\u0435\u043d\u0442\u0438\u043d\u0430. \u041f\u0440\u0438\u043c\u0435\u0440\u0430",
    "Primera Division": "\u0410\u0440\u0433\u0435\u043d\u0442\u0438\u043d\u0430. \u041f\u0440\u0438\u043c\u0435\u0440\u0430",
    "Czech First League": "\u0427\u0435\u0445\u0438\u044f. \u041b\u0438\u0433\u0430",
    "First League (Czech Republic)": "\u0427\u0435\u0445\u0438\u044f. \u041b\u0438\u0433\u0430",
    "Super League (Greece)": "\u0413\u0440\u0435\u0446\u0438\u044f. \u0421\u0443\u043f\u0435\u0440\u043b\u0438\u0433\u0430",
    "Super League 1": "\u0413\u0440\u0435\u0446\u0438\u044f. \u0421\u0443\u043f\u0435\u0440\u043b\u0438\u0433\u0430",
    "Eliteserien": "\u041d\u043e\u0440\u0432\u0435\u0433\u0438\u044f. \u042d\u043b\u0438\u0442\u0441\u0435\u0440\u0438\u044f",
    "Ekstraklasa": "\u041f\u043e\u043b\u044c\u0448\u0430. \u042d\u043a\u0441\u0442\u0440\u0430\u043a\u043b\u0430\u0441\u0430",
    "Allsvenskan": "\u0428\u0432\u0435\u0446\u0438\u044f. \u0410\u043b\u043b\u0441\u0432\u0435\u043d\u0441\u043a\u0430\u043d",
    "HNL": "\u0425\u043e\u0440\u0432\u0430\u0442\u0438\u044f. HNL",
    "Super Liga": "\u0421\u0435\u0440\u0431\u0438\u044f. \u0421\u0443\u043f\u0435\u0440\u043b\u0438\u0433\u0430",
    "NB I": "\u0412\u0435\u043d\u0433\u0440\u0438\u044f. NB I",
    "Bundesliga (Austria)": "\u0410\u0432\u0441\u0442\u0440\u0438\u044f. \u0411\u0443\u043d\u0434\u0435\u0441\u043b\u0438\u0433\u0430",
    "Premier League (Belarus)": "\u0411\u0435\u043b\u0430\u0440\u0443\u0441\u044c. \u041f\u0440\u0435\u043c\u044c\u0435\u0440",
    "Liga I": "\u0420\u0443\u043c\u044b\u043d\u0438\u044f. \u041b\u0438\u0433\u0430 I",
    "Super Liga (Slovakia)": "\u0421\u043b\u043e\u0432\u0430\u043a\u0438\u044f. \u0421\u0443\u043f\u0435\u0440\u043b\u0438\u0433\u0430",
    "PrvaLiga": "\u0421\u043b\u043e\u0432\u0435\u043d\u0438\u044f. \u041f\u0440\u0432\u0430 \u041b\u0438\u0433\u0430",
    "Premier League (Ukraine)": "\u0423\u043a\u0440\u0430\u0438\u043d\u0430. \u041f\u0440\u0435\u043c\u044c\u0435\u0440",
    "Premier Liha": "\u0423\u043a\u0440\u0430\u0438\u043d\u0430. \u041f\u0440\u0435\u043c\u044c\u0435\u0440",
    "First League (Montenegro)": "\u0427\u0435\u0440\u043d\u043e\u0433\u043e\u0440\u0438\u044f. \u041b\u0438\u0433\u0430",
    "Prva CFL": "\u0427\u0435\u0440\u043d\u043e\u0433\u043e\u0440\u0438\u044f. \u041b\u0438\u0433\u0430",
    "Championship": "\u0427\u0435\u043c\u043f\u0438\u043e\u043d\u0448\u0438\u043f",
    "EFL Championship": "\u0427\u0435\u043c\u043f\u0438\u043e\u043d\u0448\u0438\u043f",
    "Segunda Divisi\u00f3n": "\u0421\u0435\u0433\u0443\u043d\u0434\u0430",
    "Segunda Division": "\u0421\u0435\u0433\u0443\u043d\u0434\u0430",
    "Serie B": "\u0421\u0435\u0440\u0438\u044f \u0411",
    "2. Bundesliga": "\u0411\u0443\u043d\u0434\u0435\u0441\u043b\u0438\u0433\u0430 2",
    "First League (Russia)": "\u0424\u041d\u041b",
    "FNL": "\u0424\u041d\u041b",
}


def get_league_priority(league_name):
    return LEAGUE_PRIORITY_MAP.get(league_name, 99)


def translate_country(country_en):
    return COUNTRY_RU_MAP.get(country_en, country_en)


def translate_league(league_en):
    return LEAGUE_RU_MAP.get(league_en, league_en)


async def fetch_matches_from_api(date_str, limit=80):
    if not API_FOOTBALL_KEY:
        logger.error("API_FOOTBALL_KEY не задан!")
        return []
    headers = {"x-apisports-key": API_FOOTBALL_KEY}
    params = {"date": date_str}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(API_FOOTBALL_URL, headers=headers, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                data = await resp.json()
                if resp.status != 200:
                    logger.error("[API-Football] HTTP %s: %s", resp.status, data)
                    return []
                fixtures = data.get("response", [])
                if not fixtures:
                    logger.info("[API-Football] Нет матчей на %s", date_str)
                    return []
                matches = []
                for fx in fixtures:
                    league_info = fx.get("league", {})
                    league_name_en = league_info.get("name", "")
                    country_en = league_info.get("country", "")
                    priority = get_league_priority(league_name_en)
                    if priority == 99:
                        continue
                    teams = fx.get("teams", {})
                    home_name = teams.get("home", {}).get("name", "?")
                    away_name = teams.get("away", {}).get("name", "?")
                    fixture_info = fx.get("fixture", {})
                    fixture_date = fixture_info.get("date", "")
                    match_time = ""
                    if fixture_date:
                        try:
                            dt = datetime.fromisoformat(fixture_date.replace("Z", "+00:00"))
                            match_time = dt.strftime("%H:%M")
                        except Exception:
                            match_time = ""
                    country_ru = translate_country(country_en)
                    league_ru = translate_league(league_name_en)
                    matches.append({
                        "name": "{} \u2014 {}".format(home_name, away_name),
                        "country": country_ru,
                        "country_en": country_en,
                        "league": league_ru,
                        "league_en": league_name_en,
                        "match_time": match_time,
                        "priority": priority,
                        "match_date": date_str,
                    })
                matches.sort(key=lambda m: (m["priority"], m["match_time"]))
                matches = matches[:limit]
                logger.info("[API-Football] Найдено %d матчей на %s", len(matches), date_str)
                return matches
    except Exception as e:
        logger.exception("[API-Football] Исключение: %s", e)
        return []


async def save_parsed_matches_to_db(matches):
    await db_execute("DELETE FROM parsed_matches")
    if not matches:
        return
    params = []
    for m in matches:
        params.append((m["name"], m["country"], m["league"], m["match_time"], m["priority"], m["match_date"], m["country_en"], m["league_en"]))
    await db_execute_many(
        "INSERT INTO parsed_matches (name, country, league, match_time, priority, match_date, country_en, league_en) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        params
    )
    logger.info("Сохранено %d матчей в parsed_matches", len(matches))


async def move_parsed_to_matches(country, league, specific_match_id=None):
    now = datetime.now(tz).strftime("%Y-%m-%d %H:%M")
    if specific_match_id:
        rows = await db_fetchall("SELECT name, country, league, match_time FROM parsed_matches WHERE id = ?", (specific_match_id,))
    else:
        rows = await db_fetchall("SELECT name, country, league, match_time FROM parsed_matches WHERE country = ? AND league = ?", (country, league))
    if not rows:
        return 0
    params = [(r[0], r[1], r[2], r[3], now) for r in rows]
    await db_execute_many(
        "INSERT INTO matches (name, country, league, match_time, text, created_at) VALUES (?, ?, ?, ?, '', ?)",
        params
    )
    return len(rows)


# ============================================================
# ХЕНДЛЕРЫ ПАРСЕРА — вставить после admin_panel_cb
# ============================================================

@dp.callback_query(F.data == "add_match_start")
async def add_match_start(callback, state):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\U0001f50d Парсер матчей (API-Football)", callback_data="parser_date")],
        [InlineKeyboardButton(text="\u270f\ufe0f Добавить вручную", callback_data="add_match_manual")],
        [InlineKeyboardButton(text="\U0001f519 Назад", callback_data="admin_panel")]
    ])
    await callback.message.edit_text(
        "\u270f\ufe0f <b>Добавление матчей</b>\n\nВыберите способ:",
        reply_markup=kb, parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data == "add_match_manual")
async def add_match_manual(callback, state):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.message.edit_text(
        "Шаг 1/4: Введите время матча (ЧЧ:ММ) или «-» если неизвестно:",
        reply_markup=back_keyboard("add_match_start")
    )
    await state.set_state(AdminStates.add_match_time)
    await callback.answer()


@dp.callback_query(F.data == "parser_date")
async def parser_select_date(callback):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    if not API_FOOTBALL_KEY:
        await callback.answer("API_FOOTBALL_KEY не задан! Проверьте переменные окружения.", show_alert=True)
        return
    today = datetime.now(tz).date()
    tomorrow = today + timedelta(days=1)
    day_after = today + timedelta(days=2)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\U0001f4c5 Сегодня ({})".format(today.strftime("%d.%m")), callback_data="parse_{}".format(today.strftime("%Y-%m-%d")))],
        [InlineKeyboardButton(text="\U0001f4c5 Завтра ({})".format(tomorrow.strftime("%d.%m")), callback_data="parse_{}".format(tomorrow.strftime("%Y-%m-%d")))],
        [InlineKeyboardButton(text="\U0001f4c5 Послезавтра ({})".format(day_after.strftime("%d.%m")), callback_data="parse_{}".format(day_after.strftime("%Y-%m-%d")))],
        [InlineKeyboardButton(text="\U0001f519 Назад", callback_data="add_match_start")]
    ])
    await callback.message.edit_text(
        "\U0001f50d <b>Парсер матчей</b>\n\nВыберите дату:",
        reply_markup=kb, parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("parse_"))
async def parser_run(callback):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    date_str = callback.data.replace("parse_", "")
    await callback.message.edit_text("\u23f3 Загружаю матчи с API-Football...")
    await callback.answer()
    matches = await fetch_matches_from_api(date_str, limit=80)
    if not matches:
        await callback.message.edit_text(
            "\u274c Не найдено матчей по приоритетным лигам на {}.\nВозможно, в этот день нет игр топовых турниров.".format(date_str),
            reply_markup=back_keyboard("add_match_start")
        )
        return
    await save_parsed_matches_to_db(matches)
    groups = {}
    for m in matches:
        key = "{}|{}".format(m["country"], m["league"])
        if key not in groups:
            groups[key] = {"count": 0, "priority": m["priority"], "country": m["country"], "league": m["league"]}
        groups[key]["count"] += 1
    sorted_groups = sorted(groups.values(), key=lambda g: g["priority"])
    kb = []
    for g in sorted_groups:
        flag = get_flag(g["country"])
        label = "{} {} \u2014 {} ({})".format(flag, g["country"], g["league"], g["count"])
        cb_data = "pgroup_{}|{}".format(g["country"], g["league"])
        kb.append([InlineKeyboardButton(text=label, callback_data=cb_data)])
    kb.append([InlineKeyboardButton(text="\u2705 Добавить ВСЕ матчи ({} шт.)".format(len(matches)), callback_data="padd_all")])
    kb.append([InlineKeyboardButton(text="\U0001f519 Назад", callback_data="add_match_start")])
    await callback.message.edit_text(
        "\U0001f50d <b>Найдено матчей: {}</b>\n\nВыберите лигу или добавьте все сразу:".format(len(matches)),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML"
    )


@dp.callback_query(F.data.startswith("pgroup_"))
async def parser_show_group(callback):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    key = callback.data.replace("pgroup_", "", 1)
    parts = key.split("|", 1)
    if len(parts) < 2:
        await callback.answer("Ошибка", show_alert=True)
        return
    country, league = parts
    rows = await db_fetchall(
        "SELECT id, name, match_time FROM parsed_matches WHERE country = ? AND league = ? ORDER BY match_time",
        (country, league)
    )
    if not rows:
        await callback.message.edit_text("Матчей нет.", reply_markup=back_keyboard("parser_date"))
        await callback.answer()
        return
    flag = get_flag(country)
    text = "\U0001f3df {} {} \u2014 {}\n\n".format(flag, country, league)
    kb = []
    for row in rows:
        mid, name, mtime = row
        label = name
        if mtime:
            label = "\U0001f552 {} | {}".format(mtime, name)
        kb.append([InlineKeyboardButton(text=label, callback_data="pmatch_{}".format(mid))])
    kb.append([InlineKeyboardButton(text="\u2705 Добавить ВСЮ лигу ({} матчей)".format(len(rows)), callback_data="pleague_{}|{}".format(country, league))])
    kb.append([InlineKeyboardButton(text="\U0001f519 Назад", callback_data="parser_date")])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()


@dp.callback_query(F.data.startswith("pmatch_"))
async def parser_add_one(callback):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    mid = int(callback.data.replace("pmatch_", ""))
    row = await db_fetchone("SELECT name, country, league, match_time FROM parsed_matches WHERE id = ?", (mid,))
    if not row:
        await callback.answer("Матч не найден", show_alert=True)
        return
    name, country, league, mtime = row
    count = await move_parsed_to_matches(country, league, specific_match_id=mid)
    await log_admin_action(callback.from_user.id, "add_match_parser", name)
    await callback.answer("\u2705 Матч добавлен: {}".format(name), show_alert=True)


@dp.callback_query(F.data.startswith("pleague_"))
async def parser_add_league(callback):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    key = callback.data.replace("pleague_", "", 1)
    parts = key.split("|", 1)
    if len(parts) < 2:
        await callback.answer("Ошибка", show_alert=True)
        return
    country, league = parts
    count = await move_parsed_to_matches(country, league)
    await log_admin_action(callback.from_user.id, "add_league_parser", "{} - {}".format(country, league))
    await callback.answer("\u2705 Добавлено матчей: {}".format(count), show_alert=True)


@dp.callback_query(F.data == "padd_all")
async def parser_add_all(callback):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    now = datetime.now(tz).strftime("%Y-%m-%d %H:%M")
    rows = await db_fetchall("SELECT name, country, league, match_time FROM parsed_matches")
    if not rows:
        await callback.answer("Нет матчей для добавления", show_alert=True)
        return
    params = [(r[0], r[1], r[2], r[3], now) for r in rows]
    await db_execute_many(
        "INSERT INTO matches (name, country, league, match_time, text, created_at) VALUES (?, ?, ?, ?, '', ?)",
        params
    )
    await log_admin_action(callback.from_user.id, "add_all_parser", "{} matches".format(len(rows)))
    await callback.answer("\u2705 Добавлено матчей: {}".format(len(rows)), show_alert=True)


# ============================================================
# ТЕКСТЫ МАТЧЕЙ
# ============================================================

@dp.callback_query(F.data == "add_text_menu")
async def add_text_menu(callback, state):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.clear()
    rows = await db_fetchall("SELECT id, name, country, league, match_time FROM matches WHERE text = '' OR text IS NULL ORDER BY id DESC LIMIT 30")
    if not rows:
        await callback.message.edit_text(
            "\u2705 Все матчи имеют текст. Нечего редактировать.",
            reply_markup=back_keyboard("admin_panel")
        )
        await callback.answer()
        return
    kb = []
    for row in rows:
        mid, name, country, league, mtime = row
        flag = get_flag(country)
        label = "{} {} | {}".format(flag, country, name)
        if mtime:
            label += " | {}".format(mtime)
        kb.append([InlineKeyboardButton(text=label, callback_data="addtext_{}".format(mid))])
    kb.append([InlineKeyboardButton(text="\U0001f519 Назад", callback_data="admin_panel")])
    await callback.message.edit_text(
        "\u270f\ufe0f <b>Тексты матчей (без текста)</b>\n\nВыберите матч для добавления текста:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("addtext_"))
async def addtext_start(callback, state):
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    mid = int(callback.data.replace("addtext_", ""))
    row = await db_fetchone("SELECT name, country, league FROM matches WHERE id = ?", (mid,))
    if not row:
        await callback.answer("Матч не найден", show_alert=True)
        return
    name, country, league = row
    flag = get_flag(country)
    await state.update_data(text_match_id=mid)
    await callback.message.edit_text(
        "{} <b>{}</b>\n{} \u2014 {}\n\nВведите текст прогноза (одним сообщением):".format(flag, name, country, league),
        reply_markup=back_keyboard("add_text_menu"), parse_mode="HTML"
    )
    await state.set_state(AdminStates.add_text_enter)
    await callback.answer()


@dp.message(AdminStates.add_text_enter)
async def addtext_save(message, state):
    data = await state.get_data()
    mid = data.get("text_match_id")
    if not mid:
        await message.answer("Ошибка: матч не выбран.", reply_markup=main_keyboard(True))
        await state.clear()
        return
    await db_execute("UPDATE matches SET text = ? WHERE id = ?", (message.text, mid))
    await log_admin_action(message.from_user.id, "add_text", "match_id={}".format(mid))
    row = await db_fetchone("SELECT name FROM matches WHERE id = ?", (mid,))
    match_name = row[0] if row else "матч"
    await message.answer(
        "\u2705 Текст добавлен для матча: {}".format(match_name),
        reply_markup=main_keyboard(True)
    )
    await state.clear()
