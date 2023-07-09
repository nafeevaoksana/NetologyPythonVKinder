import datetime
import logging

from vk_api import vk_api, ApiError


class Api:
    RELATION_ACTIVE_SEARCH = 6
    PAGE_SIZE = 10

    def __init__(self, token):
        self.api = vk_api.VkApi(token=token)

    @staticmethod
    def __bdate_to_age(bdate):
        birth_year, = bdate.split('.')[2:3]
        return datetime.datetime.now().year - int(birth_year) if birth_year else None

    def get_profile_info(self, user_id):
        try:
            response, = self.api.method(
                'users.get',
                {
                    'user_id': user_id,
                    'fields': 'city,bdate,sex,relation,home_town'
                }
            )
            age = self.__bdate_to_age(response['bdate'])
            return {
                'name': f"{response['first_name']} {response['last_name']}",
                'id': response['id'],
                'age': age,
                'sex': response['sex'],
                'city': response.get('city', None)
            }
        except ApiError as e:
            logging.warning(e, exc_info=True)
            raise e

    def search_profiles(self, search_query, offset=0):
        try:
            response = self.api.method(
                'users.search',
                {
                    'count': self.PAGE_SIZE,
                    'offset': offset,
                    'age_from': search_query['age_from'],
                    'age_to': search_query['age_to'],
                    'sex': search_query['sex'],
                    'city': search_query['city'],
                    'status': self.RELATION_ACTIVE_SEARCH,
                    'is_closed': 0,
                    'has_photo': 1,
                    'fields': 'bdate,sex,city,photo_id'
                }
            )
            users = [
                {
                    'id': user_data['id'],
                    'name': f"{user_data['first_name']} {user_data['last_name']}",
                    'photo_id': user_data['photo_id'] if 'photo_id' in user_data else None,
                    'age': self.__bdate_to_age(user_data['bdate'])
                } for user_data in response['items']
            ]
            return users
        except ApiError as e:
            logging.warning(e, exc_info=True)
            raise e

    def get_profile_top_photos(self, user_id):
        try:
            response = self.api.method(
                'photos.get',
                {
                    'user_id': user_id,
                    'album_id': 'profile',
                    'extended': 1
                }
            )
            photos = [
                {
                    'user_id': photo['owner_id'],
                    'id': photo['id'],
                    'likes': photo['likes']['count'],
                    'comments': photo['comments']['count'],
                    'reposts': photo['reposts']['count'],
                } for photo in response['items']
            ]
            photos.sort(key=lambda photo: photo['likes'] + photo['comments'] * 5 + photo['reposts'] * 10, reverse=True)
            return photos[:3]
        except ApiError as e:
            logging.warning(e, exc_info=True)
            raise e
