# ====================== ПАРСЕР МАТЧЕЙ (API-Football) ======================
# Вставьте этот блок ПЕРЕД секцией "КЛАВИАТУРЫ" в вашем коде.

API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY", "")

# --- Маппинг названий стран (англ -> рус) ---
COUNTRY_EN_RU = {
    "England": "Англия", "Spain": "Испания", "Italy": "Италия",
    "Germany": "Германия", "France": "Франция", "Netherlands": "Нидерланды",
    "Russia": "Россия", "Portugal": "Португалия", "Belgium": "Бельгия",
    "Bulgaria": "Болгария", "Denmark": "Дания", "Switzerland": "Швейцария",
    "Turkey": "Турция", "Ireland": "Ирландия", "USA": "США",
    "Brazil": "Бразилия", "Argentina": "Аргентина",
    "Czech-Republic": "Чехия", "Czech Republic": "Чехия",
    "Greece": "Греция", "Norway": "Норвегия", "Poland": "Польша",
    "Sweden": "Швеция", "Croatia": "Хорватия", "Serbia": "Сербия",
    "Hungary": "Венгрия", "Austria": "Австрия", "Belarus": "Беларусь",
    "Romania": "Румыния", "Slovakia": "Словакия", "Slovenia": "Словения",
    "Ukraine": "Украина", "Montenegro": "Черногория",
    "World": "Мир", "Europe": "Европа",
}

# --- Маппинг названий лиг (страна_англ, лига_англ) -> русское название ---
LEAGUE_BY_PAIR = {
    # Международные (сборные)
    ("World", "World Cup"): "Чемпионат Мира",
    ("World", "World Cup - Qualification"): "ЧМ - Квалификация",
    ("Europe", "European Championship"): "Чемпионат Европы",
    ("World", "European Championship"): "Чемпионат Европы",
    ("Europe", "UEFA Nations League"): "Лига Наций",
    ("World", "UEFA Nations League"): "Лига Наций",
    ("World", "Friendlies"): "Товарищеские матчи",
    # Клубные международные
    ("Europe", "UEFA Champions League"): "Лига Чемпионов",
    ("World", "UEFA Champions League"): "Лига Чемпионов",
    ("Europe", "UEFA Europa League"): "Лига Европы",
    ("World", "UEFA Europa League"): "Лига Европы",
    ("Europe", "UEFA Europa Conference League"): "Лига Конференций",
    ("World", "UEFA Europa Conference League"): "Лига Конференций",
    # Англия
    ("England", "Premier League"): "АПЛ",
    ("England", "Championship"): "Чемпионшип",
    ("England", "League One"): "Лига 1 (Англия)",
    # Испания
    ("Spain", "La Liga"): "Ла Лига",
    ("Spain", "LaLiga"): "Ла Лига",
    ("Spain", "Segunda Division"): "Сегунда",
    ("Spain", "Segunda División"): "Сегунда",
    # Италия
    ("Italy", "Serie A"): "Серия А",
    ("Italy", "Serie B"): "Серия Б",
    # Германия
    ("Germany", "Bundesliga"): "Бундеслига",
    ("Germany", "2. Bundesliga"): "Бундеслига 2",
    # Франция
    ("France", "Ligue 1"): "Лига 1",
    # Нидерланды
    ("Netherlands", "Eredivisie"): "Эредивизи",
    # Россия
    ("Russia", "Premier League"): "РПЛ",
    ("Russia", "Premier Liga"): "РПЛ",
    ("Russia", "FNL"): "ФНЛ",
    ("Russia", "First League"): "ФНЛ",
    # Португалия
    ("Portugal", "Primeira Liga"): "Примейра-лига",
    ("Portugal", "Liga Portugal"): "Примейра-лига",
    # Другие страны
    ("Belgium", "Jupiler Pro League"): "Про-лига",
    ("Bulgaria", "First League"): "Первая лига",
    ("Denmark", "Superliga"): "Суперлига",
    ("Switzerland", "Super League"): "Суперлига",
    ("Turkey", "Super Lig"): "Суперлига",
    ("Turkey", "Süper Lig"): "Суперлига",
    ("Greece", "Super League"): "Суперлига",
    ("Austria", "Bundesliga"): "Бундеслига",
    ("Belarus", "Premier League"): "Премьер-лига",
    ("Hungary", "NB I"): "НБ I",
    ("Romania", "Liga I"): "Лига I",
    ("Serbia", "Super Liga"): "Суперлига",
    ("Slovakia", "Fortuna Liga"): "Фортунa Лига",
    ("Slovenia", "Prva Liga"): "Первая лига",
    ("Ukraine", "Premier League"): "Премьер-лига",
    ("Czech Republic", "First League"): "Первая лига",
    ("Czech-Republic", "First League"): "Первая лига",
    ("USA", "Major League Soccer"): "MLS",
    ("Brazil", "Serie A"): "Серия А",
    ("Argentina", "Liga Profesional"): "Лига Профессиональная",
    ("Norway", "Eliteserien"): "Элитсериен",
    ("Poland", "Ekstraklasa"): "Экстракласа",
    ("Sweden", "Allsvenskan"): "Алсвенскан",
    ("Croatia", "HNL"): "ХНЛ",
    ("Croatia", "First League"): "ХНЛ",
    ("Montenegro", "First League"): "Первая лига",
    ("Ireland", "Premier Division"): "Премьер-дивизион",
}

# --- Система приоритетов ---
# (приоритет, [(страна_англ, [ключевые_слова] или None), ...])
# None = любая лига из этой страны
# Проверяем в порядке: 1 → 2 → 5 → 3 → 4 (5 раньше 3, чтобы "2. Bundesliga" не поймала "Bundesliga")
PRIORITY_TIERS = [
    (1, [
        ("World", ["World Cup"]),
        ("World", ["European Championship", "Euro Championship"]),
        ("World", ["Nations League"]),
        ("Europe", ["European Championship", "Euro Championship"]),
        ("Europe", ["Nations League"]),
    ]),
    (2, [
        ("Europe", ["Champions League"]),
        ("Europe", ["Europa League"]),
        ("Europe", ["Conference League"]),
        ("World", ["Champions League"]),
        ("World", ["Europa League"]),
        ("World", ["Conference League"]),
    ]),
    (5, [
        ("England", ["Championship", "League One"]),
        ("Spain", ["Segunda", "La Liga 2", "LaLiga 2"]),
        ("Italy", ["Serie B"]),
        ("Germany", ["2. Bundesliga", "Bundesliga 2", "Second Bundesliga"]),
        ("Russia", ["FNL", "First League", "National League"]),
    ]),
    (3, [
        ("England", ["Premier League"]),
        ("Spain", ["La Liga", "LaLiga", "Primera"]),
        ("Italy", ["Serie A"]),
        ("Germany", ["Bundesliga"]),
        ("France", ["Ligue 1"]),
        ("Netherlands", ["Eredivisie"]),
        ("Russia", ["Premier League", "Premier Liga"]),
        ("Portugal", ["Primeira", "Liga Portugal"]),
    ]),
    (4, [
        ("Belgium", None), ("Bulgaria", None), ("Denmark", None),
        ("Switzerland", None), ("Turkey", None), ("Ireland", None),
        ("USA", None), ("Brazil", None), ("Argentina", None),
        ("Czech-Republic", None), ("Czech Republic", None),
        ("Greece", None), ("Norway", None), ("Poland", None),
        ("Sweden", None), ("Croatia", None), ("Serbia", None),
        ("Hungary", None), ("Austria", None), ("Belarus", None),
        ("Romania", None), ("Slovakia", None), ("Slovenia", None),
        ("Ukraine", None), ("Montenegro", None),
    ]),
]


def get_match_priority(country_en: str, league_name: str) -> int:
    """Возвращает приоритет (1-5) или 99 если лига не в системе."""
    country_lower = country_en.lower()
    league_lower = league_name.lower()
    for priority, entries in PRIORITY_TIERS:
        for entry_country, keywords in entries:
            if entry_country.lower() != country_lower:
                continue
            if keywords is None:
                return priority
            for kw in keywords:
                if kw.lower() in league_lower:
                    return priority
    return 99


def translate_country(country_en: str) -> str:
    return COUNTRY_EN_RU.get(country_en, country_en)


def translate_league(country_en: str, league_name: str) -> str:
    pair = (country_en, league_name)
    if pair in LEAGUE_BY_PAIR:
        return LEAGUE_BY_PAIR[pair]
    return league_name


async def fetch_fixtures_by_date(date_str: str) -> list:
    """Получает все матчи на дату через API-Football."""
    if not API_FOOTBALL_KEY:
        logger.error("API_FOOTBALL_KEY не задан! Получите бесплатный ключ на api-football.com")
        return []
    url = "https://v3.football.api-sports.io/fixtures"
    headers = {"x-apisports-key": API_FOOTBALL_KEY}
    params = {"date": date_str, "timezone": "Europe/Moscow"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("response", [])
                else:
                    body = await resp.text()
                    logger.error("API-Football HTTP %s: %s", resp.status, body[:300])
                    return []
    except Exception as e:
        logger.exception("API-Football: %s", e)
        return []


async def parse_and_store_matches(date_str: str) -> dict:
    """Парсит матчи, фильтрует по приоритетам, сохраняет в parsed_matches.
    Возвращает {total, stored, by_priority}.
    """
    await db_execute("DELETE FROM parsed_matches")

    fixtures = await fetch_fixtures_by_date(date_str)
    if not fixtures:
        return {"total": 0, "stored": 0, "by_priority": {}}

    all_matches = []
    for fx in fixtures:
        fixture = fx.get("fixture", {})
        league = fx.get("league", {})
        teams = fx.get("teams", {})

        # Пропускаем завершённые
        status = fixture.get("status", {}).get("short", "")
        if status in ("FT", "AET", "PEN", "AWD", "WO", "LIVE", "1H", "2H", "HT", "ET", "BT", "P"):
            continue

        country_en = league.get("country", "")
        league_name = league.get("name", "")
        home_name = teams.get("home", {}).get("name", "")
        away_name = teams.get("away", {}).get("name", "")

        if not home_name or not away_name or not country_en or not league_name:
            continue

        priority = get_match_priority(country_en, league_name)
        if priority > 5:
            continue

        match_time = ""
        try:
            dt_str = fixture.get("date", "")
            if dt_str:
                dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                dt_moscow = dt.astimezone(tz)
                match_time = dt_moscow.strftime("%H:%M")
        except Exception:
            pass

        all_matches.append({
            "name": "{} — {}".format(home_name, away_name),
            "country": translate_country(country_en),
            "league": translate_league(country_en, league_name),
            "time": match_time,
            "priority": priority,
            "country_en": country_en,
            "league_en": league_name,
        })

    # Сортируем по приоритету, берём <= 80
    all_matches.sort(key=lambda x: x["priority"])
    all_matches = all_matches[:80]

    for m in all_matches:
        await db_execute(
            "INSERT INTO parsed_matches (name, country, league, match_time, priority, "
            "match_date, country_en, league_en) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (m["name"], m["country"], m["league"], m["time"],
             m["priority"], date_str, m["country_en"], m["league_en"])
        )

    by_priority = {}
    for m in all_matches:
        by_priority[m["priority"]] = by_priority.get(m["priority"], 0) + 1

    return {"total": len(fixtures), "stored": len(all_matches), "by_priority": by_priority}


async def add_parsed_match_to_main(parsed_id: int) -> bool:
    """Переносит матч из parsed_matches в matches. Возвращает True если добавлен."""
    row = await db_fetchone(
        "SELECT name, country, league, match_time FROM parsed_matches WHERE id = ?",
        (parsed_id,)
    )
    if not row:
        return False
    name, country, league, mtime = row
    # Проверяем дубликат
    dup = await db_fetchone(
        "SELECT 1 FROM matches WHERE name = ? AND country = ? AND league = ? AND match_time = ?",
        (name, country, league, mtime)
    )
    if dup:
        await db_execute("DELETE FROM parsed_matches WHERE id = ?", (parsed_id,))
        return False
    now = datetime.now(tz).strftime("%Y-%m-%d %H:%M")
    await db_execute(
        "INSERT INTO matches (name, country, league, match_time, text, created_at) "
        "VALUES (?, ?, ?, ?, '', ?)",
        (name, country, league, mtime, now)
    )
    await db_execute("DELETE FROM parsed_matches WHERE id = ?", (parsed_id,))
    return True


async def add_league_to_main(country: str, league: str) -> int:
    """Переносит все матчи лиги из parsed_matches в matches. Возвращает кол-во добавленных."""
    rows = await db_fetchall(
        "SELECT id FROM parsed_matches WHERE country = ? AND league = ?",
        (country, league)
    )
    count = 0
    for r in rows:
        if await add_parsed_match_to_main(r[0]):
            count += 1
    return count


# ====================== ХЕНДЛЕРЫ ПАРСЕРА ======================
# Вставьте этот блок ПОСЛЕ секции "АДМИН ПАНЕЛЬ" (после handler'а admin_panel_cb).


@dp.callback_query(F.data == "add_match_start")
async def add_match_start_new(callback: types.CallbackQuery, state: FSMContext):
    """Вместо ручного ввода — показываем выбор: парсер или вручную."""
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Парсер матчей", callback_data="parser_start")],
        [InlineKeyboardButton(text="📝 Добавить вручную", callback_data="add_match_manual")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
    ])
    await callback.message.edit_text("Выберите способ добавления матчей:", reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data == "add_match_manual")
async def add_match_manual(callback: types.CallbackQuery, state: FSMContext):
    """Старый ручной ввод — шаг 1/4."""
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.message.edit_text(
        "Шаг 1/4: Введите время матча в формате ЧЧ:ММ (например: 18:30).\n"
        "Если время неизвестно — введите «-»",
        reply_markup=back_keyboard("add_match_start")
    )
    await state.set_state(AdminStates.add_match_time)
    await callback.answer()


@dp.callback_query(F.data == "parser_start")
async def parser_start(callback: types.CallbackQuery, state: FSMContext):
    """Запуск парсера — выбор даты."""
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.clear()
    today = datetime.now(tz).date()
    tomorrow = today + timedelta(days=1)
    after = today + timedelta(days=2)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="📅 Сегодня ({})".format(today.strftime("%d.%m")),
            callback_data="psdate_{}".format(today.strftime("%Y-%m-%d"))
        )],
        [InlineKeyboardButton(
            text="📅 Завтра ({})".format(tomorrow.strftime("%d.%m")),
            callback_data="psdate_{}".format(tomorrow.strftime("%Y-%m-%d"))
        )],
        [InlineKeyboardButton(
            text="📅 Послезавтра ({})".format(after.strftime("%d.%m")),
            callback_data="psdate_{}".format(after.strftime("%Y-%m-%d"))
        )],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="add_match_start")]
    ])
    await callback.message.edit_text(
        "🔍 <b>Парсер матчей</b>\n\nВыберите дату:", reply_markup=kb, parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("psdate_"))
async def parser_run(callback: types.CallbackQuery):
    """Запуск парсинга для выбранной даты."""
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    if not API_FOOTBALL_KEY:
        await callback.message.edit_text(
            "❌ Не задан API_FOOTBALL_KEY!\n\n"
            "Получите бесплатный ключ на https://www.api-football.com/ "
            "(100 запросов/день бесплатно) и добавьте в переменные окружения.",
            reply_markup=back_keyboard("add_match_start")
        )
        await callback.answer()
        return

    date_str = callback.data.replace("psdate_", "")
    await callback.message.edit_text("⏳ Парсинг матчей на {}...".format(date_str))
    await callback.answer()

    result = await parse_and_store_matches(date_str)

    if result["stored"] == 0:
        await callback.message.edit_text(
            "Матчей по приоритетным лигам на {} не найдено.\n"
            "(Всего матчей в API: {})".format(date_str, result["total"]),
            reply_markup=back_keyboard("add_match_start")
        )
        return

    # Показываем лиги по приоритету
    await parser_show_leagues(callback.message, date_str, result)


async def parser_show_leagues(message, date_str: str, result: dict = None):
    """Показывает список лиг, сгруппированных по приоритету."""
    rows = await db_fetchall(
        "SELECT DISTINCT country, league, priority FROM parsed_matches "
        "ORDER BY priority, country, league"
    )
    if not rows:
        await message.edit_text(
            "Все матчи уже добавлены или список пуст.",
            reply_markup=back_keyboard("admin_panel")
        )
        return

    # Группируем по приоритету
    priority_names = {1: "🌍 Международные", 2: "🏆 Клубные междунар.", 3: "⭐ Топ-лиги",
                      4: "⚽ Национальные", 5: "📉 Вторые дивизионы"}

    text_parts = ["🔍 <b>Парсер матчей</b> — {}\n".format(date_str)]
    if result:
        stats_line = "Найдено: {} матчей в {} лигах".format(result["stored"], len(rows))
        text_parts.append(stats_line + "\n")

    kb = []
    current_priority = None
    for country, league, priority in rows:
        if priority != current_priority:
            current_priority = priority
            pname = priority_names.get(priority, "Другие")
            count_in_p = sum(1 for r in rows if r[2] == priority)
            text_parts.append("\n{} — {} лиг:".format(pname, count_in_p))

        # Считаем матчи в этой лиге
        count_rows = await db_fetchall(
            "SELECT COUNT(*) FROM parsed_matches WHERE country = ? AND league = ?",
            (country, league)
        )
        count = count_rows[0][0] if count_rows else 0
        flag = get_flag(country)
        label = "{} {} — {} ({})".format(flag, country, league, count)
        cb_data = "psleague_{}|{}".format(country, league)
        kb.append([InlineKeyboardButton(text=label, callback_data=cb_data)])
        text_parts.append("  {} {} — {} ({} матчей)".format(flag, country, league, count))

    kb.append([InlineKeyboardButton(text="✅ Готово", callback_data="psdone")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="add_match_start")])

    full_text = "\n".join(text_parts)
    if len(full_text) > 4000:
        full_text = full_text[:4000] + "\n..."

    await message.edit_text(full_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")


@dp.callback_query(F.data.startswith("psleague_"))
async def parser_show_league_matches(callback: types.CallbackQuery):
    """Показывает матчи внутри конкретной лиги."""
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    key = callback.data.replace("psleague_", "", 1)
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
        await callback.message.edit_text(
            "В этой лиге матчей не осталось.", reply_markup=back_keyboard("psback_leagues")
        )
        await callback.answer()
        return

    flag = get_flag(country)
    text = "🏟 {} {} — {}\n\nМатчи:".format(flag, country, league)
    kb = []
    for row in rows:
        mid, name, mtime = row
        label = name
        if mtime:
            label = "🕒 {} | {}".format(mtime, name)
        kb.append([InlineKeyboardButton(text=label, callback_data="psmatch_{}".format(mid))])

    kb.append([InlineKeyboardButton(
        text="✅ Добавить всю лигу ({})".format(len(rows)),
        callback_data="psall_{}|{}".format(country, league)
    )])
    kb.append([InlineKeyboardButton(text="🔙 К списку лиг", callback_data="psback_leagues")])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()


@dp.callback_query(F.data == "psback_leagues")
async def parser_back_to_leagues(callback: types.CallbackQuery):
    """Возврат к списку лиг — перечитываем parsed_matches."""
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    # Находим дату из parsed_matches
    row = await db_fetchone("SELECT match_date FROM parsed_matches LIMIT 1")
    date_str = row[0] if row else ""
    if date_str:
        await parser_show_leagues(callback.message, date_str)
    else:
        await callback.message.edit_text(
            "Список пуст. Запустите парсер заново.",
            reply_markup=back_keyboard("add_match_start")
        )
    await callback.answer()


@dp.callback_query(F.data.startswith("psmatch_"))
async def parser_select_match(callback: types.CallbackQuery):
    """Добавляет один матч в основную базу."""
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    pid = int(callback.data.replace("psmatch_", ""))
    added = await add_parsed_match_to_main(pid)
    if added:
        await log_admin_action(callback.from_user.id, "parser_add_match", str(pid))
        await callback.answer("✅ Матч добавлен!")
    else:
        await callback.answer("Матч уже добавлен или не найден")
    # Обновляем список матчей в лиге
    await parser_show_league_matches(callback)


@dp.callback_query(F.data.startswith("psall_"))
async def parser_select_league(callback: types.CallbackQuery):
    """Добавляет все матчи лиги в основную базу."""
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    key = callback.data.replace("psall_", "", 1)
    parts = key.split("|", 1)
    if len(parts) < 2:
        await callback.answer("Ошибка", show_alert=True)
        return
    country, league = parts
    count = await add_league_to_main(country, league)
    await log_admin_action(callback.from_user.id, "parser_add_league", "{}|{}".format(country, league))
    await callback.answer("✅ Добавлено матчей: {}".format(count), show_alert=True)
    # Возврат к списку лиг
    row = await db_fetchone("SELECT match_date FROM parsed_matches LIMIT 1")
    date_str = row[0] if row else ""
    if date_str:
        await parser_show_leagues(callback.message, date_str)
    else:
        await callback.message.edit_text(
            "Все матчи добавлены! 🎉\n\nТеперь можете добавить текст к каждому матчу.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📝 Тексты матчей", callback_data="add_text_menu")],
                [InlineKeyboardButton(text="🔙 Админ-панель", callback_data="admin_panel")]
            ])
        )


@dp.callback_query(F.data == "psdone")
async def parser_done(callback: types.CallbackQuery):
    """Завершение парсинга — показываем что добавлено и опцию текстов."""
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    # Считаем сколько матчей без текста
    no_text = await db_fetchone(
        "SELECT COUNT(*) FROM matches WHERE text = '' OR text IS NULL"
    )
    no_text_count = no_text[0] if no_text else 0
    await db_execute("DELETE FROM parsed_matches")  # очищаем временную таблицу

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Тексты матчей ({})".format(no_text_count), callback_data="add_text_menu")],
        [InlineKeyboardButton(text="🔙 Админ-панель", callback_data="admin_panel")]
    ])
    await callback.message.edit_text(
        "✅ Парсинг завершён!\n\n"
        "Матчей без текста: {}\n"
        "Добавьте текст к каждому матчу через кнопку ниже.".format(no_text_count),
        reply_markup=kb
    )
    await callback.answer()


# ====================== ТЕКСТЫ МАТЧЕЙ ======================

@dp.callback_query(F.data == "add_text_menu")
async def add_text_menu(callback: types.CallbackQuery):
    """Показывает матчи без текста для добавления."""
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    rows = await db_fetchall(
        "SELECT id, name, country, league, match_time FROM matches "
        "WHERE text = '' OR text IS NULL ORDER BY id DESC"
    )
    if not rows:
        await callback.message.edit_text(
            "✅ Все матчи уже имеют текст.",
            reply_markup=back_keyboard("admin_panel")
        )
        await callback.answer()
        return

    text = "📝 <b>Матчи без текста</b> ({})\n\nНажмите на матч, чтобы добавить текст:".format(len(rows))
    kb = []
    for row in rows:
        mid, name, country, league, mtime = row
        flag = get_flag(country)
        label = "{} {}".format(flag, name)
        if mtime:
            label = "🕒 {} | {}".format(mtime, name)
        kb.append([InlineKeyboardButton(text=label, callback_data="txtmatch_{}".format(mid))])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data.startswith("txtmatch_"))
async def txtmatch_select(callback: types.CallbackQuery, state: FSMContext):
    """Выбор матча для ввода текста."""
    if str(callback.from_user.id) not in admin_users:
        await callback.answer("Нет доступа", show_alert=True)
        return
    mid = int(callback.data.replace("txtmatch_", ""))
    row = await db_fetchone(
        "SELECT name, country, league, match_time FROM matches WHERE id = ?", (mid,)
    )
    if not row:
        await callback.answer("Матч не найден", show_alert=True)
        return
    name, country, league, mtime = row
    flag = get_flag(country)
    info = "{} {}".format(flag, name)
    if mtime:
        info = "🕒 {} | {}".format(mtime, name)
    await state.update_data(txt_match_id=mid)
    await callback.message.edit_text(
        "📝 Введите текст для матча:\n<b>{}</b>\n{} — {}\n\nОтправьте текст одним сообщением:".format(info, country, league),
        reply_markup=back_keyboard("add_text_menu"),
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.add_text_enter)
    await callback.answer()


@dp.message(AdminStates.add_text_enter)
async def add_text_enter(message: types.Message, state: FSMContext):
    """Сохраняет введённый текст для матча."""
    data = await state.get_data()
    mid = data.get("txt_match_id")
    if not mid:
        await message.answer("Ошибка: матч не выбран.", reply_markup=main_keyboard(True))
        await state.clear()
        return
    await db_execute("UPDATE matches SET text = ? WHERE id = ?", (message.text, mid))
    await log_admin_action(message.from_user.id, "add_text", str(mid))
    await message.answer("✅ Текст добавлен!", reply_markup=main_keyboard(True))
    await state.clear()
