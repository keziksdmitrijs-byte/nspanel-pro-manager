# NSPanel Pro Manager

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/)
[![Validate](https://github.com/keziksdmitrijs-byte/nspanel-pro-manager/actions/workflows/validate.yml/badge.svg)](https://github.com/keziksdmitrijs-byte/nspanel-pro-manager/actions/workflows/validate.yml)

Home Assistant integration that turns a fresh **Sonoff NSPanel Pro** into a ready wall panel with one click — enter the IP address, press *Submit*, and the panel is set up over ADB:

- installs **Home Assistant Companion** (minimal flavour) and **[NSPanel Pro Tools](https://github.com/seaky/nspanel_pro_tools_apk)** if they are missing;
- configures NSPanel Pro Tools: wake on hand wave (proximity), dimmed screensaver, auto start of Home Assistant after boot, MQTT broker address and Home Assistant discovery;
- clean screen by default (no Android navigation bar and no eWeLink floating circle), screen never switches off by Android, brightness;
- opens your dashboard on the panel;
- nightly reboot at a chosen time, settings are re-applied automatically after every reboot.

Works great together with [NSPanel Pro Card](https://github.com/keziksdmitrijs-byte/nspanel-pro-card).

*Русская версия ниже.*

## Requirements

- NSPanel Pro (86 / 120) with **ADB over network enabled** (eWeLink app → panel → Settings → developer options / ADB; port 5555).
- Root (`su`) on the panel is recommended — it is needed to write NSPanel Pro Tools settings. Without root everything else still works.
- Home Assistant 2025.3 or newer. For proximity wake: the **Mosquitto broker** add‑on and the **MQTT** integration.

## Installation

1. HACS → ⋮ → *Custom repositories* → `https://github.com/keziksdmitrijs-byte/nspanel-pro-manager`, category **Integration**.
2. Install **NSPanel Pro Manager** and restart Home Assistant.
3. *Settings → Devices & services → Add integration → NSPanel Pro Manager*.
4. Enter the IP address of the panel, the dashboard path (for example `nspanel-pro/home`) and keep **Set up the panel now** on.
5. If the panel shows *Allow USB debugging?* — tick *Always allow* and press **OK** (within 30 s).

The setup runs in the background (the *Setup running* sensor is on). When it is finished you get a notification with what was done and what is left to do:

- **MQTT login** — open NSPanel Pro Tools on the panel → *integration → MQTT → Setup*, enter the MQTT user name and password, switch *Enabled* on. Credentials are never stored by this integration.
- On the panel log in to Home Assistant (if asked) and in the app settings set the dashboard as the default for this device.

A panel that is already set up can be added the same way — nothing is reinstalled, only the settings are applied. A replacement panel: add it with its new IP; settings are stored per panel.

## Entities

| Entity | Description |
| --- | --- |
| Switch *Control buttons and circle* | Show/hide the Android navigation bar and the eWeLink floating circle (off = clean panel) |
| Switch *Screensaver* | Dim the panel after inactivity (NSPanel Pro Tools) |
| Number *Screensaver after* | Inactivity time in seconds (Tools supports 15 s … 30 min, the nearest value is used) |
| Number *Screen brightness* / *Screensaver brightness* | Brightness in % |
| Switch *Nightly reboot* + Time *Reboot time* | Reboot every night |
| Number *Proximity threshold* | Wake-on-wave sensitivity: raw sensor value above which a wave is detected. Lower = more sensitive, higher = you must come closer. `0` = NSPanel Pro Tools default |
| Button *Measure proximity (10 s)* + sensor *Proximity peak* | Press, then wave your hand at the distance that should wake the panel. The sensor shows the peak, the background level (`idle`) and a `suggested_threshold` |
| Buttons | Open dashboard, Restart Home Assistant app, Screen on/off, Reboot, Open NSPanel Pro Tools, Set up panel |
| Binary sensors | ADB connection, Screen, Setup running |
| Diagnostic sensors | IP address, Last boot, raw brightness, app / Tools / WebView versions, foreground app |

Use the screensaver switch and timeout in the card (entity ids depend on the panel name and the Home Assistant language):

```yaml
screensaver:
  enabled: true
  enabled_entity: switch.nspanel_pro_screensaver
  timeout_entity: number.nspanel_pro_screensaver_after
```

### Proximity sensitivity

1. Press **Measure proximity (10 s)** and during 10 seconds wave your hand at the distance from which the panel should wake up.
2. Look at **Proximity peak**: the state is the highest value, attribute `idle` is the background noise (about 25–35 on NSPanel Pro 86), `suggested_threshold` is halfway between them.
3. Set **Proximity threshold** to the suggested value (or a bit lower for more sensitivity). The value must stay clearly above `idle`, otherwise the panel wakes up by itself.

## Services

- `nspanel_pro.provision` — run the full setup again (optionally for selected panels).
- `nspanel_pro.shell` — run an ADB shell command; returns the output (`response_variable`).

```yaml
action: nspanel_pro.shell
data:
  command: settings get system screen_brightness
response_variable: out
```

## Options

*Configure* on the integration: dashboard path, MQTT broker address/port (empty = this Home Assistant), Home Assistant app package (`io.homeassistant.companion.android.minimal` or `io.homeassistant.companion.android`), whether to install the apps.

---

# NSPanel Pro Manager (RU)

Интеграция Home Assistant, которая превращает новую **Sonoff NSPanel Pro** в готовую настенную панель одной кнопкой: вписываете IP, нажимаете «Отправить» — и панель настраивается по ADB:

- ставит **Home Assistant Companion** и **NSPanel Pro Tools**, если их нет;
- настраивает NSPanel Pro Tools: пробуждение взмахом руки, приглушённая заставка, автозапуск Home Assistant после загрузки, адрес MQTT‑брокера и автообнаружение в HA;
- по умолчанию чистый экран (без кнопок Android и без плавающего круга eWeLink), экран не гаснет, яркость;
- открывает ваш дашборд на панели;
- ночная перезагрузка в выбранное время, после каждой перезагрузки настройки применяются снова.

## Требования

- На панели включён **ADB по сети** (eWeLink → панель → настройки → режим разработчика / ADB, порт 5555).
- Желателен root (`su`) — нужен для записи настроек NSPanel Pro Tools. Без root всё остальное работает.
- Home Assistant 2025.3+. Для пробуждения взмахом — дополнение **Mosquitto broker** и интеграция **MQTT**.

## Установка

1. HACS → ⋮ → *Пользовательские репозитории* → `https://github.com/keziksdmitrijs-byte/nspanel-pro-manager`, категория **Integration**.
2. Установите **NSPanel Pro Manager** и перезапустите Home Assistant.
3. *Настройки → Устройства и службы → Добавить интеграцию → NSPanel Pro Manager*.
4. Введите IP панели, путь дашборда (например `nspanel-pro/home`), оставьте включённым **Настроить панель сейчас**.
5. Если на панели появится «Разрешить отладку по USB?» — отметьте «Всегда разрешать» и нажмите **OK** (в течение 30 с).

Настройка идёт в фоне (датчик «Идёт настройка» включён). В конце придёт уведомление: что сделано и что осталось:

- **Логин MQTT** — на панели откройте NSPanel Pro Tools → *integration → MQTT → Setup*, введите логин и пароль MQTT и включите *Enabled*. Интеграция пароли не хранит.
- На панели войдите в Home Assistant (если попросит) и в настройках приложения сделайте дашборд основным для этого устройства.

Уже настроенную панель можно добавить так же — ничего не переустанавливается, только применяются настройки. Новая панель на замену — просто добавьте её по новому IP.

## Сущности

Переключатели «Кнопки управления и круг», «Заставка», «Ночная перезагрузка»; числа «Яркость экрана», «Яркость на заставке», «Заставка через»; время «Время перезагрузки»; кнопки «Открыть дашборд», «Перезапустить приложение HA», «Включить/Выключить экран», «Перезагрузить», «Открыть NSPanel Pro Tools», «Настроить панель»; датчики связи, экрана, настройки и диагностические датчики (IP, последняя загрузка, версии приложений, WebView).

### Чувствительность датчика приближения

Число «Порог приближения» — значение датчика, выше которого считается, что поднесли руку. Меньше — чувствительнее (срабатывает издалека), больше — нужно подойти ближе. `0` — значение по умолчанию NSPanel Pro Tools.

1. Нажмите «Измерить приближение (10 с)» и в течение 10 секунд помашите рукой на том расстоянии, с которого панель должна просыпаться.
2. Датчик «Пик приближения» покажет максимум, атрибут `idle` — фоновый уровень (около 25–35), `suggested_threshold` — рекомендуемый порог посередине.
3. Впишите рекомендуемое значение в «Порог приближения». Порог должен быть заметно выше `idle`, иначе панель будет просыпаться сама.

## Службы

- `nspanel_pro.provision` — запустить полную настройку ещё раз.
- `nspanel_pro.shell` — выполнить ADB‑команду и получить вывод.

## License

MIT
