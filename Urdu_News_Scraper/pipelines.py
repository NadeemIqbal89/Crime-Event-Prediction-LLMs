# FYP_Scraper/FYP_Scraper/pipelines.py

import pymongo
from itemadapter import ItemAdapter
from scrapy.exceptions import DropItem
from dotenv import load_dotenv
from urllib.parse import quote_plus
import os
import sys
import dns.resolver

dns.resolver.default_resolver = dns.resolver.Resolver()
dns.resolver.default_resolver.nameservers = ['8.8.8.8']

class MongoDBPipeline:
    def __init__(self):
        load_dotenv()
        username = quote_plus(os.getenv("MONGODB_USERNAME"))
        password = quote_plus(os.getenv("MONGODB_PASSWORD"))
        self.mongo_uri = f"mongodb+srv://{username}:{password}@cluster0.66sawpl.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
        self.client = None
        self.db = None
        self.consecutive_updates = 0  # Track consecutive updates

    def open_spider(self, spider):
        try:
            self.client = pymongo.MongoClient(self.mongo_uri)
            self.db = self.client['news_db']
            spider.logger.info("Connected to MongoDB successfully!")
        except Exception as e:
            spider.logger.error(f"MongoDB Connection Error: {str(e)}")
            raise

    def process_item(self, item, spider):
        adapter = ItemAdapter(item)
        
        required_fields = ['title', 'content', 'date', 'url', 'source']
        missing_fields = [field for field in required_fields 
                         if not adapter.get(field) or adapter.get(field).strip() == '']
        
        if missing_fields:
            error_msg = f"Missing or empty required fields: {', '.join(missing_fields)}"
            spider.logger.error(f"Item dropped - {error_msg}")
            spider.logger.error(f"URL: {adapter.get('url', 'No URL')}")
            raise DropItem(error_msg)

        try:
            source = adapter.get('source', 'unknown')
            collection_name = f"{source}_raw"
            
            collection = self.db[collection_name]
            
            collection.create_index([('url', pymongo.ASCENDING)], unique=True)
            
            result = collection.update_one(
                {'url': adapter['url']},
                {'$set': adapter.asdict()},
                upsert=True
            )
            
            if result.upserted_id:
                spider.logger.info(f"New article saved to {collection_name}: {adapter['url']}")
                self.consecutive_updates = 0  
            else:
                self.consecutive_updates += 1  
                spider.logger.info(f"Article updated in {collection_name}: {adapter['url']} (Consecutive updates: {self.consecutive_updates})")
                
                if self.consecutive_updates >= 10:
                    spider.logger.info(f"Exiting after {self.consecutive_updates} consecutive updates")
                    print("Exiting after 10 consecutive updates...")
                    os._exit(0)
                
            return item

        except pymongo.errors.DuplicateKeyError:
            spider.logger.warning(f"Duplicate article found: {adapter['url']}")
            raise DropItem(f"Duplicate article found: {adapter['url']}")
            
        except Exception as e:
            spider.logger.error(f"MongoDB Error processing {adapter.get('url', 'No URL')}: {str(e)}")
            raise DropItem(f"MongoDB Error: {str(e)}")

    def close_spider(self, spider):
        if self.client:
            self.client.close()
            spider.logger.info("MongoDB connection closed")


class WeatherMongoDBPipeline:
    def __init__(self):
        load_dotenv()
        username = quote_plus(os.getenv("MONGODB_USERNAME"))
        password = quote_plus(os.getenv("MONGODB_PASSWORD"))
        self.mongo_uri = f"mongodb+srv://{username}:{password}@cluster0.66sawpl.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
        self.client = None
        self.db = None

    def open_spider(self, spider):
        try:
            self.client = pymongo.MongoClient(self.mongo_uri)
            self.db = self.client['weather_db']  # New database for weather data
            spider.logger.info("Connected to Weather MongoDB successfully!")
        except Exception as e:
            spider.logger.error(f"Weather MongoDB Connection Error: {str(e)}")
            raise

    def process_item(self, item, spider):
        adapter = ItemAdapter(item)
        
        # Check if this is a WeatherDataItem
        if 'unique_id' not in adapter:
            return item  # Skip if not a weather item
        
        required_fields = ['unique_id', 'date', 'time', 'temperature_high', 'location']
        missing_fields = [field for field in required_fields 
                         if not adapter.get(field) or adapter.get(field).strip() == '']
        
        if missing_fields:
            error_msg = f"Missing or empty required fields: {', '.join(missing_fields)}"
            spider.logger.error(f"Weather item dropped - {error_msg}")
            raise DropItem(error_msg)

        try:
            collection_name = 'weather_data'
            collection = self.db[collection_name]
            
            # Create unique index on unique_id
            collection.create_index([('unique_id', pymongo.ASCENDING)], unique=True)
            
            # Create compound index for efficient querying
            collection.create_index([
                ('location', pymongo.ASCENDING),
                ('year', pymongo.ASCENDING),
                ('month', pymongo.ASCENDING),
                ('day_number', pymongo.ASCENDING)
            ])
            
            result = collection.update_one(
                {'unique_id': adapter['unique_id']},
                {'$set': adapter.asdict()},
                upsert=True
            )
            
            if result.upserted_id:
                spider.logger.info(f"New weather record saved: {adapter['unique_id']}")
            else:
                spider.logger.info(f"Weather record updated: {adapter['unique_id']}")
                
            return item

        except pymongo.errors.DuplicateKeyError:
            spider.logger.warning(f"Duplicate weather record found: {adapter['unique_id']}")
            raise DropItem(f"Duplicate weather record found: {adapter['unique_id']}")
            
        except Exception as e:
            spider.logger.error(f"Weather MongoDB Error processing {adapter.get('unique_id', 'No ID')}: {str(e)}")
            raise DropItem(f"Weather MongoDB Error: {str(e)}")

    def close_spider(self, spider):
        if self.client:
            self.client.close()
            spider.logger.info("Weather MongoDB connection closed")
