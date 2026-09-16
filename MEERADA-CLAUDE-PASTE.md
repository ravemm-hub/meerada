# Meerada — הוראות ביצוע לקלוד קוד (הדבק כמו שזה)
תאריך: 2026-09-15
Repo: C:\Users\rave\Desktop\handover | GitHub: ravemm-hub/meerada
כללים: CLAUDE.md (ruff, mypy --strict, pytest ירוק, בלי מפתחות בלוג, בלי הוצאות בלי אישור מפורש)

## הקשר מוצר
- Meerada = בורסת מודלים + LLManager + Guard + Cross-check + Handshake באתר meerada.app
- Meerada Tribes = אפליקציית הצ'אטים בטלפון (לשעבר Tryber) — רק לתקן קופי באתר, לא לגעת במובייל
- הפצה/מרקטינג מושהים עד שהמוצר עובד

## QA חי — מה עובד (אל תשבור)
- דפי האתר 200; grade_state.json + models_live.json חיים; CI שעתי מצליח
- בורסה: ~353 מודלים ברשימה, חיפוש/פילטר/השוואה עובדים; Frontier/Labs/New/Outcome מאוכלסים
- ~7 מודלים מדורגים עם score+CPAT חי (למשל groq/compound-mini ~93.5)
- CLI meerada (up/guard/crosscheck/…) עובד מקומית
- pytest ירוק; Guard חוסם סודות שנראים אמיתיים
- Desktop release v0.2.10 ב-GitHub Releases (Win/Mac/Linux)
- Hosted LLManager: demo חינמי על Groq/Auto רץ בהצלחה
- דפי guard/pricing/llmanager נטענים

## QA חי — מה שבור (לתקן לפי סדר)

### P0.1 התקנה מהאתר (חלקית כבר תוקנה)
- היה: בדף הבית `pip install meerada` אבל ב-PyPI אין חבילה meerada (404). יש handover אחר ב-PyPI שלא קשור.
- תוקן ב-master + gh-pages: CTA מצביע ל-GitHub Releases + `pip install "meerada @ git+https://github.com/ravemm-hub/meerada"`.
- עדיין לעשות:
  1. לאחד קופי ב-llmanager.html / index.template.html / README כדי שלא יישארו הנחיות שבורות
  2. אופציונלי חזק: לפרסם חבילת `meerada` אמיתית ל-PyPI (בלי להתנגש עם handover הזר)

### P0.2 כיסוי דירוג דל מדי לבורסה
- ב-grade_state יש ~30 כרטיסים ורק ~7 עם score אמיתי
- ב-GitHub Secrets יש רק OPENROUTER_API_KEY
- לוודא שה-grader ב-`.github/workflows/grade.yml` ובקוד bench צורך כשקיימים:
  GROQ_API_KEY, GOOGLE_API_KEY, GH_MODELS_TOKEN, CEREBRAS_API_KEY, MISTRAL_API_KEY
- לא להמציא מפתחות. אם חוטים חסרים — חבר אותם. אם חסרים רק secrets — תעד ב-docs/LAUNCH.md איך owner שם אותם מ-Desktop\Meerada\keys\

### P0.3 First paint של הבורסה
- בלי JS / בטעינה איטית הטבלאות נראות ריקות → הורג אמון
- להטמיע ב-index.html (או בבילד דיפלוי) את מובילי ה-score+CPAT מ-grade_state.json
- ברירת מחדל: רק מודלים עם score; להסתיר/לכווץ n=0 provisional

### P0.4 app.meerada.app — סיפור Login לא תואם מציאות
- /me מחזיר auth=false, user=local
- ב-HTML יש Google Sign-in אבל הפריסה לא במצב hosted אמיתי
- או להפעיל OAuth+vault כמו שמובטח בקופי, או להוריד את הבטחת "Real Google sign-in" מהטסטר הפתוח

### P0.5 Dead end ב-meerada up בלי מפתחות
- /models: connected=[], live=false
- קוקפיט עם empty-state ברור: כפתורים למפתחות free (Groq/Google/GitHub) + אי אפשר לשלוח בלי מפתח בלי הודעה מובנת
- אופציה: MEERADA_LOCAL_VAULT=1 כברירת מחדל ל-local כדי לשמור מפתחות

### P0.6 Tribes store links
- tribes.html iPhone CTA → App Store 404: https://apps.apple.com/app/id6780445573
- Android CTA נפתח כ-Tryber-Soci (com.tryber.social), לא Meerada Tribes
- לתקן: iOS — Coming soon / TestFlight במקום 404 (עדיין בביקורת); אנדרואיד — ליישר ברנדינג ל-Meerada Tribes כשאפשר

### P0.7 Dead Handshake CTA בדף הבית
- "Run the real Handshake" מצביע ל-index.html#download אבל אין עוגן #download → קופץ לראש הדף
- לתקן לקישור אמיתי ל-Handshake / llmanager handshake

### P0.8 Guard false positive ב-LLManager hosted
- אחרי reload, משימה שהושלמה מראה guard: STUCK / "task looks stuck"
- לחקור stall detector אחרי idle/reload; לנקות STUCK כשהתשובה הושלמה

### P1
- Tribes naming: Tryber→Meerada Tribes בקופי ציבורי באתר
- grade.html: כתוב CONFIRMED 0 / PROVISIONAL 30 מול ~7 שורות מוצגות — ליישר קופי/מכנה
- T22 hallucination column אם P0 נגמר
- Handshake / Cross-check E2E עם מפתח free אחד — מסלול: רואה CPAT → מריץ מודל אחד

## אל תעשה
- אל תאמן judge (T23) / אל תוציא כסף על GPU בלי כן מפורש
- אל תחזיר תמחור בתשלום ל-UI
- אל תיגע ב-Tribes mobile repo
- אל תדפיס/תקבע מפתחות בקומיטים

## הגדרת סיום
- התקנה מהאתר עובדת (installer או pip git) — אין CTA ל-404
- בורסה מציגה מובילים אמיתיים מיד; grader מוכן לספקי free נוספים ברגע שיש secrets
- app.meerada.app והקופי מסונכרנים; Guard לא מסמן STUCK שווא
- Tribes CTAs לא שבורים; Handshake CTA עובד
- ruff + mypy + pytest ירוקים; קומיטים קטנים; push ל-master + deploy site ל-gh-pages תוך שימור grade_state.json / models_live.json