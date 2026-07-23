# Define here the models for your scraped items
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/items.html

import scrapy
from w3lib.html import remove_tags
from datetime import datetime
from itemloaders.processors import TakeFirst, MapCompose, Join


def clean_text(text):
    if text:
        return remove_tags(text).strip()
    return ''

class NewsArticleItem(scrapy.Item):
    title = scrapy.Field(
        input_processor=MapCompose(str.strip),
        output_processor=TakeFirst())

    content = scrapy.Field(
        input_processor=MapCompose(clean_text),
        output_processor=Join()
    )

    date = scrapy.Field(
        input_processor=MapCompose(str.strip),
        output_processor=TakeFirst()
    )

    url = scrapy.Field(
        output_processor=TakeFirst()
    )

    source = scrapy.Field(
        input_processor=MapCompose(str.strip),
        output_processor=TakeFirst()
    )

    reported_time = scrapy.Field(
        input_processor=MapCompose(str.strip),
        output_processor=TakeFirst()
    )
    
    category = scrapy.Field(
        input_processor=MapCompose(str.strip),
        output_processor=TakeFirst(),
        default='N/A'
    )


class WeatherDataItem(scrapy.Item):
    unique_id = scrapy.Field(
        output_processor=TakeFirst()
    )
    
    date = scrapy.Field(
        input_processor=MapCompose(str.strip),
        output_processor=TakeFirst()
    )
    
    time = scrapy.Field(
        input_processor=MapCompose(str.strip),
        output_processor=TakeFirst()
    )
    
    day_number = scrapy.Field(
        input_processor=MapCompose(str.strip),
        output_processor=TakeFirst()
    )
    
    temperature_high = scrapy.Field(
        input_processor=MapCompose(str.strip),
        output_processor=TakeFirst()
    )
    
    temperature_low = scrapy.Field(
        input_processor=MapCompose(str.strip),
        output_processor=TakeFirst()
    )
    
    weather_condition = scrapy.Field(
        input_processor=MapCompose(str.strip),
        output_processor=TakeFirst()
    )
    
    humidity = scrapy.Field(
        input_processor=MapCompose(str.strip),
        output_processor=TakeFirst()
    )
    
    wind_speed = scrapy.Field(
        input_processor=MapCompose(str.strip),
        output_processor=TakeFirst()
    )
    
    pressure = scrapy.Field(
        input_processor=MapCompose(str.strip),
        output_processor=TakeFirst()
    )
    
    visibility = scrapy.Field(
        input_processor=MapCompose(str.strip),
        output_processor=TakeFirst()
    )
    
    location = scrapy.Field(
        input_processor=MapCompose(str.strip),
        output_processor=TakeFirst()
    )
    
    month = scrapy.Field(
        input_processor=MapCompose(str.strip),
        output_processor=TakeFirst()
    )
    
    year = scrapy.Field(
        input_processor=MapCompose(str.strip),
        output_processor=TakeFirst()
    )
    
    url = scrapy.Field(
        output_processor=TakeFirst()
    )
    
    scraped_at = scrapy.Field(
        output_processor=TakeFirst()
    )

