from vk_api import vk_api, ApiError
from vk_api.longpoll import VkLongPoll, VkEventType
from vk_api.utils import get_random_id

from Api import Api
from Database import Database
from config import COMMUNITY_TOKEN, USER_TOKEN, DB_URL_OBJECT


class ChatBot:
    AGE_DIFF = 3
    SEX_FEMALE = 1
    SEX_MALE = 2
    MESSAGES = {
        'unknown_command': 'Простите, я вас не понял. Можете узнать что я умею командой "помощь"',
        'internal_error': 'Простите, я не смог выполнить ваш запрос',
        'whoami_change_profile': 'Если требуется, можете изменить данные командами "пол" и "возвраст"',
        'profile_update_success': 'Ваш {field} успешно изменен на {value}',
        'profile_update_failure': 'Простите, мне не удалость изменить ваш {field}',
        'profile_update_unknown_value': 'Простите, но я вас не понял, напишите {field} в формате {format}',
        'profile_update_unknown_field': 'Простите, но я не знаю такого поля',
        'profile_update_unknown_format': 'Напишите в формате "поле значение"',
        'search_next_profile': 'Для просмотра следующего профиля напишите "дальше" или "следующий/ая"',
        'missing_profile_fields_warning': 'У вас не заполнены следующие данные профиля: {missing_fields}.\nЗаполните '
                                          'их чтобы улучшить результаты поиска.\n',
        'profile_photos_unavailable': 'Не удалось получить фото профиля, возможно пользователь скрыл их'
    }
    COMMANDS = {
        'whoami': {'кто я', 'мой профиль', 'обо мне'},
        'start_search': {'поиск', 'начать поиск', 'следующий', 'cледующая', 'дальше'},
        'help': {'привет', 'помощь', 'что умеешь', 'кто ты'},
        'profile_data': {'возраст', 'пол'},
    }
    profile_info = None
    offset = 0
    found_profiles = []

    @staticmethod
    def __any_substring(value, str_list):
        return any(map(value.__contains__, str_list))

    @staticmethod
    def __profile_missing_fields(profile_info):
        missing_fields = set()
        if not profile_info['age']:
            missing_fields.add('age')
        if not profile_info['sex']:
            missing_fields.add('sex')
        if not profile_info['city']:
            pass
        return missing_fields

    def __init__(self, community_token, user_token, db_connection_string):
        self.vk = vk_api.VkApi(token=community_token)
        self.api = Api(token=user_token)
        self.db = Database(connection_string=db_connection_string)

    def __send_message(self, user_id, message, attachment=None):
        if not message and not attachment:
            return
        data = {
            'user_id': user_id,
            'message': message,
            'random_id': get_random_id()
        }
        if attachment:
            data['attachment'] = attachment
        self.vk.method('messages.send', data)

    def listen(self):
        long_poll = VkLongPoll(self.vk)
        try:
            for event in long_poll.listen():
                if event.type == VkEventType.MESSAGE_NEW and event.text and event.to_me:
                    self.__process_new_message(event)
        except KeyboardInterrupt:
            pass

    def __process_new_message(self, event):
        command = event.text.strip().lower()
        if self.__any_substring(command, self.COMMANDS['whoami']):
            self.__process_whoami_command(event)
        elif self.__any_substring(command, self.COMMANDS['start_search']):
            self.__process_start_search_command(event)
        elif self.__any_substring(command, self.COMMANDS['help']):
            self.__process_help_command(event)
        elif self.__any_substring(command, self.COMMANDS['profile_data']):
            self.__process_profile_data_command(command, event)
        else:
            self.__send_message(event.user_id, self.MESSAGES['unknown_command'])

    def __get_profile_info(self, user_id):
        if self.profile_info is None:
            self.profile_info = self.api.get_profile_info(user_id)

        return self.profile_info

    def __update_profile_info(self, new_profile_info):
        if self.profile_info is None:
            self.profile_info = new_profile_info
        else:
            self.profile_info['name'] = new_profile_info['name']
            self.profile_info['city'] = new_profile_info['city']
            if 'sex' in new_profile_info:
                self.profile_info['sex'] = new_profile_info['sex']
            if 'age' in new_profile_info:
                self.profile_info['age'] = new_profile_info['age']

    def __process_whoami_command(self, event):
        user_id = event.user_id
        try:
            profile_info = self.__get_profile_info(user_id)
            profile_representation = self.__profile_to_str(profile_info)
            message = profile_representation + '\n' + self.MESSAGES['whoami_change_profile']
            self.__send_message(user_id, message)
        except ApiError:
            self.__send_message(user_id, self.MESSAGES['internal_error'])

    @staticmethod
    def __profile_filed_to_str(field):
        if field == 'sex':
            return 'пол'
        if field == 'age':
            return 'возраст'
        return ""

    def __search_profiles(self, user_id, profile_info):
        age_from = profile_info['age'] - self.AGE_DIFF if profile_info['age'] else None
        age_to = age_from + self.AGE_DIFF * 2 if age_from else None
        city = profile_info['city']['id'] if profile_info['city'] else None
        if profile_info['sex'] == self.SEX_FEMALE:
            sex = self.SEX_MALE
        elif profile_info['sex'] == self.SEX_MALE:
            sex = self.SEX_FEMALE
        else:
            sex = None

        filtered_profiles = []
        while not filtered_profiles:
            profiles = self.api.search_profiles(
                {
                    'age_from': age_from,
                    'age_to': age_to,
                    'sex': sex,
                    'city': city,
                },
                offset=self.offset
            )

            if not profiles:
                break

            self.offset += len(profiles)

            filtered_profiles = list(
                filter(
                    lambda user: not self.db.is_profile_viewed(user_id, user['id']),
                    profiles
                )
            )
        return filtered_profiles

    def __get_next_profile(self, user_id, profile_info):
        try:
            return self.found_profiles.pop()
        except IndexError:
            self.found_profiles = self.__search_profiles(user_id, profile_info)
            if not self.found_profiles:
                return None

            return self.found_profiles.pop()

    def __get_next_profile_message(self, next_profile):
        if next_profile is None:
            next_profile_data = 'Больше профилей не найдено.'
            attachment = None
        else:
            next_profile_data = self.__profile_to_str(next_profile)
            try:
                photos = self.api.get_profile_top_photos(next_profile['id'])[:3]
                attachment = ','.join([f"photo{photo['user_id']}_{photo['id']}" for photo in photos])
            except ApiError:
                next_profile_data += '\n' + self.MESSAGES['profile_photos_unavailable']
                attachment = None
        return next_profile_data, attachment

    def __process_start_search_command(self, event):
        user_id = event.user_id
        try:
            profile_info = self.__get_profile_info(event.user_id)
            missing_fields = self.__profile_missing_fields(profile_info)
            if missing_fields:
                missing_fields_message = self.MESSAGES['missing_profile_fields_warning'].format(
                    missing_fields=', '.join(
                        [self.__profile_filed_to_str(missing_field) for missing_field in missing_fields]
                    )
                )
            else:
                missing_fields_message = ''

            next_profile = self.__get_next_profile(user_id, profile_info)
            next_profile_data, attachment = self.__get_next_profile_message(next_profile)
            message = missing_fields_message + next_profile_data
            self.__send_message(user_id, message, attachment=attachment)
            self.db.insert_viewed_profile(user_id, next_profile['id'])
        except ApiError:
            self.__send_message(user_id, self.MESSAGES['internal_error'])

    def __process_help_command(self, event):
        help_message = f"Возможные команды: " + ', '.join(
            [text for values in self.COMMANDS.values() for text in values])
        self.__send_message(event.user_id, help_message)

    def __process_profile_data_command(self, command: str, event):
        def update_failure_message(field):
            return self.MESSAGES['profile_update_failure'].format(field=field)

        def update_success_message(field, value):
            return self.MESSAGES['profile_update_success'].format(field=field, value=value)

        def unknown_value_message(field, format):
            return self.MESSAGES['profile_update_unknown_value'].format(field=field, format=format)

        user_id = event.user_id
        try:
            field, value = command.split(' ')
        except ValueError:
            self.__send_message(user_id, self.MESSAGES['profile_update_unknown_format'])
            return

        profile_info = self.__get_profile_info(user_id)
        if field == 'возраст':
            try:
                age = int(value)
                profile_info['age'] = age
                self.__update_profile_info(profile_info)
                message = update_success_message(field, age)
            except ValueError:
                message = unknown_value_message(field, 'число')
        elif field == 'пол':
            if value.startswith('ж'):
                sex = self.SEX_FEMALE
            elif value.startswith('м'):
                sex = self.SEX_MALE
            else:
                sex = None
            if sex is not None:
                profile_info['sex'] = sex
                self.__update_profile_info(profile_info)
                message = update_success_message(field, self.__sex_to_str(sex))
            else:
                message = unknown_value_message(field, 'мужской/женский')
        else:
            message = self.MESSAGES['profile_update_unknown_field']
        self.__send_message(user_id, message)

    @staticmethod
    def __sex_to_str(sex):
        if sex == ChatBot.SEX_FEMALE:
            return 'женский'
        elif sex == ChatBot.SEX_MALE:
            return 'мужской'
        else:
            return None

    @staticmethod
    def __profile_to_str(profile_info):
        sex = ChatBot.__sex_to_str(profile_info.get('sex', None))
        city = profile_info['city']['title'] if profile_info.get('city', None) else None
        data = [f"{profile_info['name']}"]
        if sex:
            data.append(f"Пол: {sex}")
        if profile_info['age']:
            data.append(f"Возраст: {profile_info['age']}")
        if city:
            data.append(f"Город {city}")
        data.append(f"Ссылка на профиль: https://vk.com/id{profile_info['id']}")
        return '\n'.join(data)


if __name__ == '__main__':
    bot = ChatBot(COMMUNITY_TOKEN, USER_TOKEN, DB_URL_OBJECT)
    bot.listen()
