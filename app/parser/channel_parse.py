import time
from datetime import datetime, timezone
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
from copy import copy
import logging
import re

logger = logging.getLogger(__name__)

def setup_driver():
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument('--disable-blink-features=AutomationControlled')

    try:
        service = ChromeService(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver
    except Exception as e:
        logger.error(f"Ошибка при инициализации драйвера: {e}")
        return None

def parse_post_content(full_text: str):
    """Очистка текста поста с фильтрацией служебной информации"""
    if not full_text or not full_text.strip():
        return ""
    
    lines = [line.strip() for line in full_text.split('\n') if line.strip()]
    
    if not lines:
        return ""
    
    # Фильтруем служебные строки
    filtered_lines = []
    skip_patterns = [
        r'^\d+:\d+$',  # Время типа "0:25", "12:34"
        r'^\d+[KMB]?\s*(views?|просмотр.*)?$',  # Счётчики просмотров
        r'^This media is not supported',  # Служебные сообщения
        r'^(Edited|Forwarded from)',  # Метаданные
        r'^[❤️🔥💥✨🎯👉👈📌⚡️]+$',  # Только эмодзи
    ]
    
    for line in lines:
        is_service = False
        for pattern in skip_patterns:
            if re.match(pattern, line, re.IGNORECASE):
                is_service = True
                break
        
        if not is_service and len(line) > 1:
            filtered_lines.append(line)
    
    if not filtered_lines:
        return ""
    
    result = "\n".join(filtered_lines)
    
    # Финальная проверка: хотя бы 5 символов текста
    clean_text = ''.join(c for c in result if c.isalnum() or c.isspace())
    
    if len(clean_text.strip()) < 5:
        return ""
    
    return result

def extract_post_datetime(post_div):
    """Извлечение даты поста"""
    all_time_tags = post_div.find_all('time')
    for tag in all_time_tags:
        dt = tag.get('datetime')
        if dt:
            return dt
    
    date_link = post_div.select_one('a.tgme_widget_message_date')
    if date_link:
        time_tag = date_link.find('time')
        if time_tag and time_tag.get('datetime'):
            return time_tag.get('datetime')
    
    service_msg = post_div.select_one('.tgme_widget_message_service_date')
    if service_msg:
        time_tag = service_msg.find('time')
        if time_tag and time_tag.get('datetime'):
            return time_tag.get('datetime')
    
    for attr in ['data-datetime', 'data-time', 'data-timestamp']:
        if post_div.get(attr):
            return post_div.get(attr)
    
    return None

def extract_text_from_post(post_div):
    """Извлечение текста из поста"""
    post_div = copy(post_div)

    for unwanted in post_div.select(
        '.tgme_widget_message_reply, '
        '.tgme_widget_message_reply_text'
    ):
        unwanted.decompose()

    text_fragments = []
    
    # 1. Основной текст
    main_text = post_div.select_one('.tgme_widget_message_text')
    if main_text:
        text = main_text.get_text(separator='\n', strip=True)
        if text:
            text_fragments.append(text)
    
    # 2. Подписи к медиа
    for selector in [
        '.tgme_widget_message_caption',
        '.tgme_widget_message_photo_caption',
        '.tgme_widget_message_video_caption',
        '.tgme_widget_message_document_caption'
    ]:
        elements = post_div.select(selector)
        for elem in elements:
            text = elem.get_text(separator='\n', strip=True)
            if text and text not in text_fragments:
                text_fragments.append(text)
    
    # 3. Медиа-группа
    media_group = post_div.select_one('.tgme_widget_message_grouped_layer')
    if media_group:
        group_text = media_group.get_text(separator='\n', strip=True)
        if group_text and group_text not in text_fragments:
            text_fragments.append(group_text)
    
    # 4. Превью ссылок
    link_previews = post_div.select('.tgme_widget_message_link_preview')
    for preview in link_previews:
        title = preview.select_one('.link_preview_title, .tgme_widget_message_link_preview_title')
        desc = preview.select_one('.link_preview_description, .tgme_widget_message_link_preview_description')
        
        if title:
            text = title.get_text(strip=True)
            if text and text not in text_fragments:
                text_fragments.append(text)
        if desc:
            text = desc.get_text(strip=True)
            if text and text not in text_fragments:
                text_fragments.append(text)
    
    # 5. Опросы
    poll_question = post_div.select_one('.tgme_widget_message_poll_question')
    if poll_question:
        text = poll_question.get_text(strip=True)
        if text and text not in text_fragments:
            text_fragments.append(text)
    
    poll_options = post_div.select('.tgme_widget_message_poll_option_text')
    for option in poll_options:
        text = option.get_text(strip=True)
        if text and text not in text_fragments:
            text_fragments.append(text)
    
    # 6. Пересланные сообщения
    forwarded_text = post_div.select_one('.tgme_widget_message_forwarded_from_text')
    if forwarded_text:
        text = forwarded_text.get_text(strip=True)
        if text and text not in text_fragments:
            text_fragments.append(text)
    
    # 7. ЗАПАСНОЙ ВАРИАНТ
    if not text_fragments:
        message_bubble = post_div.select_one('.tgme_widget_message_bubble')
        if message_bubble:
            for unwanted in message_bubble.select('.tgme_widget_message_video_wrap, .tgme_widget_message_photo_wrap, .tgme_widget_message_document_wrap, .tgme_widget_message_audio, .tgme_widget_message_voice, '
                                                  '.tgme_widget_message_reply, .tgme_widget_message_reply_text'):
                unwanted.decompose()
            
            fallback_text = message_bubble.get_text(separator='\n', strip=True)
            
            if fallback_text:
                lines = []
                skip_keywords = ['views', 'view', 'edited', 'forwarded from', 'forwarded', 'reply', 'this media is not supported']
                
                for line in fallback_text.split('\n'):
                    line = line.strip()
                    
                    if len(line) < 3:
                        continue
                    
                    if any(skip.lower() in line.lower() for skip in skip_keywords):
                        continue
                    
                    if re.match(r'^(\d+:\d+|\d+[KMB]?)$', line):
                        continue
                    
                    lines.append(line)
                
                if lines:
                    text_fragments.append('\n'.join(lines))
    
    if text_fragments:
        unique_texts = []
        seen = set()
        for text in text_fragments:
            normalized = text.lower().strip()
            if normalized not in seen and len(normalized) > 0:
                seen.add(normalized)
                unique_texts.append(text)
        return "\n\n".join(unique_texts)
    
    return ""

def parse_channel_web(channel_username: str, start_dt: datetime = None, end_dt: datetime = None):
    """
    Парсинг канала Telegram через веб-интерфейс
    КЛЮЧЕВОЕ ИЗМЕНЕНИЕ: прокручиваем ВВЕРХ, а не вниз!
    """
    driver = setup_driver()
    if not driver:
        logger.error("Не удалось инициализировать драйвер")
        return []

    final_results = []
    processed_post_ids = set()
    url = f"https://t.me/s/{channel_username}"

    logger.info(f"Начинаем парсинг канала: {channel_username}")
    logger.info(f"Диапазон дат: с {start_dt} по {end_dt}")

    try:
        driver.get(url)
        time.sleep(5)

        scroll_attempts = 0
        max_scroll_attempts = 200  # Увеличили для больших каналов
        no_new_content_count = 0
        max_no_new_content = 5
        
        reached_start_date = False

        while scroll_attempts < max_scroll_attempts and not reached_start_date:
            scroll_attempts += 1

            soup = BeautifulSoup(driver.page_source, 'html.parser')
            # all_posts = soup.select('div.tgme_widget_message_wrap')
            #
            # logger.info(f"Попытка {scroll_attempts}: найдено {len(all_posts)} постов на странице (обработано ранее: {len(processed_post_ids)})")
            #
            # if not all_posts:
            #     logger.warning("Посты не найдены на странице")
            #     break
            #
            # new_posts_in_this_iteration = 0
            #
            # for post_wrap in all_posts:
            from copy import copy

            all_posts = soup.select('div.tgme_widget_message_wrap')
            all_posts_copy = [copy(post) for post in all_posts]  # Копия списка
            print(all_posts)
            logger.info(
                f"Попытка {scroll_attempts}: найдено {len(all_posts)} постов на странице (обработано ранее: {len(processed_post_ids)})")

            if not all_posts:
                logger.warning("Посты не найдены на странице")
                break

            new_posts_in_this_iteration = 0

            # Используем копию, оригинал останется неизменным
            for post_wrap in all_posts_copy:
                post_div = post_wrap.find('div', class_='tgme_widget_message')
                if not post_div:
                    continue

                date_link = post_div.select_one('a.tgme_widget_message_date')
                if not date_link or not date_link.get('href'):
                    continue

                post_id = date_link['href'].split('/')[-1]
                
                if post_id in processed_post_ids:
                    continue

                processed_post_ids.add(post_id)
                new_posts_in_this_iteration += 1

                datetime_str = extract_post_datetime(post_div)
                
                if not datetime_str:
                    logger.warning(f"Пост {post_id}: не найдена дата")
                    if start_dt or end_dt:
                        continue
                    post_datetime = None
                else:
                    try:
                        if datetime_str.endswith('Z'):
                            datetime_str = datetime_str[:-1] + '+00:00'
                        post_datetime = datetime.fromisoformat(datetime_str)
                        
                        if post_datetime.tzinfo is None:
                            post_datetime = post_datetime.replace(tzinfo=timezone.utc)
                        
                        # Проверка: достигли ли начальной даты
                        if start_dt and post_datetime < start_dt:
                            logger.info(f"Пост {post_id} ({post_datetime.strftime('%Y-%m-%d')}) старше начальной даты {start_dt.strftime('%Y-%m-%d')}")
                            reached_start_date = True
                            # НЕ break здесь - обрабатываем все посты на текущей странице
                        
                        # Пропускаем посты вне диапазона
                        if start_dt and post_datetime < start_dt:
                            continue
                        if end_dt and post_datetime > end_dt:
                            continue
                            
                    except Exception as e:
                        logger.error(f"Ошибка парсинга даты {datetime_str}: {e}")
                        if start_dt or end_dt:
                            continue
                        post_datetime = None
                print(all_posts)
                full_text = extract_text_from_post(post_div)
                parsed_content = parse_post_content(full_text)

                if parsed_content:
                    result_item = {
                        "post_id": post_id,
                        "content": parsed_content
                    }
                    
                    if post_datetime:
                        result_item["datetime"] = post_datetime.strftime("%Y-%m-%d %H:%M:%S")
                        logger.info(f"✅ Найден пост {post_id} от {post_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
                    else:
                        result_item["datetime"] = "Unknown"
                        logger.info(f"✅ Найден пост {post_id} (дата неизвестна)")
                    
                    final_results.append(result_item)
                else:
                    logger.debug(f"❌ Пост {post_id} отфильтрован")

            # Если достигли начальной даты - прекращаем
            if reached_start_date:
                logger.info("Достигнута начальная дата, завершаем парсинг")
                break

            # Логика повторных попыток
            if new_posts_in_this_iteration == 0:
                no_new_content_count += 1
                logger.info(f"Новых постов не найдено ({no_new_content_count}/{max_no_new_content})")
            else:
                no_new_content_count = 0
                logger.info(f"Найдено {new_posts_in_this_iteration} новых постов в этой итерации")
            
            if no_new_content_count >= max_no_new_content:
                logger.info("Достигнут лимит попыток без новых постов, завершаем парсинг")
                break
            
            # ⚠️ КЛЮЧЕВОЕ ИЗМЕНЕНИЕ: ПРОКРУЧИВАЕМ ВВЕРХ!
            logger.debug("Прокручиваем страницу вверх для загрузки старых постов...")
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(3)  # Даём время на загрузку
            
            # Дополнительная прокрутка для надёжности
            driver.execute_script("window.scrollTo(0, 200);")
            time.sleep(0.5)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

        logger.info(f"Парсинг завершен. Обработано {len(processed_post_ids)} постов, из них подходящих: {len(final_results)}")

        # Сортируем по дате (от новых к старым)
        final_results.sort(key=lambda x: x['datetime'] if x['datetime'] != 'Unknown' else '0000-00-00', reverse=True)

        if not final_results:
            logger.warning("Подходящих постов не найдено.")

        return final_results

    except Exception as e:
        logger.error(f"Произошла ошибка во время парсинга: {e}")
        import traceback
        traceback.print_exc()
        return []
    finally:
        if driver:
            driver.quit()

def get_channel_info_web(channel_username: str):
    driver = setup_driver()
    if not driver:
        return None

    try:
        url = f"https://t.me/s/{channel_username}"
        driver.get(url)
        time.sleep(3)

        soup = BeautifulSoup(driver.page_source, 'html.parser')

        name_tag = soup.select_one('div.tgme_channel_info_header_title > span')
        count_tag = soup.select_one('.tgme_channel_info_counter .counter_value')

        if not name_tag:
            return None

        name = name_tag.get_text(strip=True)
        participants_count = count_tag.get_text(strip=True) if count_tag else 'N/A'

        return {
            "name": name,
            "username": channel_username,
            "participants_count": participants_count
        }
    except Exception as e:
        logger.error(f"Ошибка при получении информации о канале ({channel_username}): {e}")
        return None
    finally:
        if driver:
            driver.quit()

# Для отладки
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    start_date = datetime(2025, 12, 30, tzinfo=timezone.utc)
    end_date = datetime(2026, 2, 2, 23, 59, 59, tzinfo=timezone.utc)

    print(f"Парсим канал Viktor_Komendov_SE с {start_date} по {end_date}")

    posts = parse_channel_web("bookinema", start_date, end_date)

    print(f"\n{'='*80}")
    print(f"ИТОГО НАЙДЕНО ПОСТОВ: {len(posts)}")
    print('='*80)

    for i, post in enumerate(posts[:10], 1):
        print(f"\n=== Пост {i} ===")
        print(f"ID: {post['post_id']}")
        print(f"Дата: {post['datetime']}")
        # content_preview = post['content'][:200] + "..." if len(post['content']) > 200 else post['content']
        content_preview = post['content']
        print(f"Текст ({len(post['content'])} символов):\n{content_preview}")
        print("-" * 80)