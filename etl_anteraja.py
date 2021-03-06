# -*- coding: utf-8 -*-
"""ETL-Anteraja

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1R6M38V5CM6gXriMgBi1zA2wslh7pZ0MQ

# **Pre-ETL**

### **Library Installation**
"""

!pip install pyspark

!pip install google-play-scraper

!pip install deep-translator

!pip install tweet-preprocessor

!pip install emoji

!pip install azure-storage-blob==2.1.0

"""### **Importing Libraries**"""

# PySpark
from pyspark.sql import SparkSession
from pyspark.sql.types import StringType, IntegerType, StructType, StructField, TimestampType, FloatType
from pyspark.sql.functions import udf, col

# Scraping Libraries
import tweepy as tw
from google_play_scraper import app, Sort, reviews_all

# Text Processing Libraries
from deep_translator import GoogleTranslator
from textblob import TextBlob
from nltk.corpus import stopwords
import re
import nltk
import preprocessor as p
import emoji

# Load Libraries with Azure Storage Blob
from azure.storage.blob import (
    BlockBlobService
)
import io

import pandas as pd
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt

"""### **API Key**"""

#Insert API Key File
APIKey = pd.read_csv('APIKey.csv')

"""Twitter Key"""

# API key, API secret, access token, access token secret
API_KEY = APIKey['TwitterKey'][0]
API_SECRET = APIKey['TwitterSecret'][0]
ACCESS_TOKEN = APIKey['TwitterToken'][0]
ACCESS_TOKEN_SECRET = APIKey['TwitterTokenSecret'][0]

# Authentification
auth = tw.OAuthHandler(API_KEY, API_SECRET)
auth.set_access_token(ACCESS_TOKEN, ACCESS_TOKEN_SECRET)

# API
api = tw.API(auth, wait_on_rate_limit=True)

"""Azure Storage"""

accountName = APIKey['AzureName'][0]
accountKey = APIKey['AzurekKey'][0]
containerName = APIKey['AzureContainer'][0]

"""### **Creating Spark Session**"""

spark = SparkSession.builder.appName("AnterajaRevs").getOrCreate()

"""### **Some Configurations**"""

p.set_options(p.OPT.MENTION, p.OPT.EMOJI, p.OPT.HASHTAG, p.OPT.RESERVED, p.OPT.SMILEY, p.OPT.URL)
nltk.download('words')
words = set(nltk.corpus.words.words())

"""# **Extract**

### **A. Scraping Twitter Data**
"""

# Define the search term and the date_since date as variables
search_words = "anteraja -from:anteraja_id lang:id"
date_year = "2021"
date_month = "10"
date_days = range(10, 18)
date_time = "2315"
screen_name = []
text = []
created_at = []

for date_day in date_days:
  date_since = date_year + date_month + str(date_day) + date_time 
  date_until = date_year + date_month + str(date_day+1) + date_time

  tweets = tw.Cursor(api.search_full_archive,
                    environment_name="TwitterResearch",
                    query=search_words,
                    fromDate=date_since,
                    toDate=date_until).items(100)
  
  for tweet in tweets:
    screen_name.append(tweet.user.screen_name)
    text.append(tweet.text)
    created_at.append(tweet.created_at)

tweet_data = pd.DataFrame(
    {'username': screen_name,
     'date': created_at,
     'tweet': text
    })

tweet_data

# Defining Spark schema
schema_twt = 'username STRING, date TIMESTAMP, tweet STRING'

# Converting data type of 'date' column from string to datetime
tweet_data['date'] = pd.to_datetime(tweet_data['date'])

# Creating Spark dataframe using defined schema
df_Twitter = spark.createDataFrame(tweet_data[['username', 'date', 'tweet']], schema_twt)

df_Twitter.printSchema()

df_Twitter.show(n=2)

"""### **B. Scraping Google Play Store Review**"""

id_reviews = reviews_all(
                        'id.anteraja.aca',
                        sleep_milliseconds=0, # defaults to 0
                        lang='en', # defaults to 'en'
                        country='id', # defaults to 'us'
                        sort=Sort.NEWEST, # defaults to Sort.MOST_RELEVANT
                        )

# Defining Spark schema
schema_ps = 'userName STRING, at TIMESTAMP, content STRING'

df_google_play = pd.DataFrame(np.array(id_reviews), columns=['review'])
df_google_play = df_google_play.join(pd.DataFrame(df_google_play.pop('review').tolist()))

# Converting data type of 'at' column from string to datetime
df_google_play['at'] = pd.to_datetime(df_google_play['at'])

# Creating Spark dataframe using defined schema
df_google_play = spark.createDataFrame(df_google_play[['userName', 'at', 'content']], schema_ps)

df_google_play.printSchema()

df_google_play.show(n=2)

"""# **Transform**

### **A. Creating Functions**

#### **1. Defining Translator Function**
"""

def translator(text):
  text = GoogleTranslator(source='id', target='en').translate(text)
  return text

"""#### **2. Defining Cleansing Function**"""

def cleaner(text):
    text = re.sub("@[A-Za-z0-9]+", "", text) #Remove @ sign
    text = ''.join(c for c in text if c not in emoji.UNICODE_EMOJI) #Remove Emojis
    text = text.replace("#", "").replace("_", "") #Remove hashtag sign but keep the text
    text = " ".join(w for w in nltk.wordpunct_tokenize(text) \
         if w.lower() in words or not w.isalpha()) #Remove non-english tweets (not 100% success)
    return text

udf_clean = udf(lambda x:cleaner(x), StringType())

"""#### **3. Defining Sentiment Score Function**"""

def sentiment_score(text):
  blob = TextBlob(str(text))
  score = blob.polarity
  return score

udf_sentiment_score = udf(lambda x:sentiment_score(x), FloatType())

"""#### **4. Defining Sentiment Analysis Function**"""

def sentiment(sentiment_score):
   if sentiment_score > 0:
    return "positive"
   elif sentiment_score < 0:
    return "negative"
   else:
    return "neutral"  

udf_sentiment = udf(lambda x:sentiment(x), StringType())

"""### **B. Applying Functions to Twitter Data**"""

#Create pandas DataFrame, to avoid exceeding rate limit on Google Translator Rate Limit
pd_Twitter = pd.DataFrame(df_Twitter.toPandas()) 
pd_Twitter.head()

# Applying Translator Function (Pandas)
pd_Twitter['tweet'] = pd_Twitter['tweet'].map(lambda x: translator(x))

pd_Twitter.tail()

#Turn Pandas to Spark (For Faster Computation)
df_Twitter=spark.createDataFrame(pd_Twitter)

# Applying Cleansing Function
df_Twitter = df_Twitter.withColumn("tweet", udf_clean(col("tweet"))).select("username", "date", "tweet")

df_Twitter.show(n=5)

# Applying Sentiment Score Function
df_Twitter = df_Twitter.withColumn("sentiment_score", udf_sentiment_score(col("tweet"))).select("username", "date", "tweet", "sentiment_score")

df_Twitter.show(n=5)

# Applying Sentiment Analysis Function
df_Twitter = df_Twitter.withColumn("sentiment", udf_sentiment(col("sentiment_score"))).select("username", "date", "tweet", "sentiment_score", "sentiment")

df_Twitter.show(n=7)

export_Twitter = df_Twitter.select("username", "date", "tweet", "sentiment_score", "sentiment")

#Create pandas DataFrame, to export data
pd_Twitter = pd.DataFrame(export_Twitter.toPandas())

"""### **C. Applying Functions to Google Play Store Review Data**"""

#Create pandas DataFrame, to avoid exceeding rate limit on Google Translator Rate Limit
pd_google_play = pd.DataFrame(df_google_play.toPandas()) 
pd_google_play.head()

pd_google_play = pd_google_play[pd_google_play['at'].dt.strftime('%Y-%m-%d') >= "2021-11-11"]
pd_google_play

#Translate from pandas dataframe to GoogleTranslator API
pd_google_play['content'] = pd_google_play['content'].map(lambda x: translator(x))

pd_google_play.tail()

pd_google_play = pd_google_play[pd_google_play['content'].notna()]

pd_google_play.head()

#Turn Pandas to Spark (For Faster Computation)
df_google_play=spark.createDataFrame(pd_google_play)

df_google_play.show(2)

# Applying Cleansing Function
df_google_play = df_google_play.withColumn("content", udf_clean(col("content"))).select("userName", "at", "content")

df_google_play.show(5)

# Applying Sentiment Score Function
df_google_play = df_google_play.withColumn("sentiment_score", udf_sentiment_score(col("content"))).select("userName", "at", "content", "sentiment_score")

df_google_play.show(n=5)

# Applying Sentiment Category Function
df_google_play = df_google_play.withColumn("sentiment", udf_sentiment(col("sentiment_score"))).select("userName", "at", "content", "sentiment_score", "sentiment")

df_google_play.show(n=5)

export_google_play = df_google_play.select("userName", "at", "content", "sentiment_score", "sentiment")

#Create pandas DataFrame, to export data
pd_google_play = pd.DataFrame(export_google_play.toPandas())

"""# **Load**"""

#Load Twitter data (pd_Twitter) to Azure Storage

loadTwitter = io.StringIO()
loadTwitter = pd_Twitter.to_csv(index_label="idx", encoding = "utf-8")

blobService = BlockBlobService(account_name=accountName, account_key=accountKey)
blobService.create_blob_from_text(containerName, 'TwitterSentimentAnalysis.csv', loadTwitter)

#Load Twitter data (pd_Twitter) to Azure Storage

loadPlaystore = io.StringIO()
loadPlaystore = pd_google_play.to_csv(index_label="idx", encoding = "utf-8")

blobService = BlockBlobService(account_name=accountName, account_key=accountKey)
blobService.create_blob_from_text(containerName, 'PlaystoreSentimentAnalysis.csv', loadPlaystore)

"""# **Basic Viz**

### **A. Twitter Sentiment Analysis**
"""

tmp_Twitter = pd_Twitter.groupby(pd_Twitter.date.dt.day).agg('mean')

tmp_Twitter = tmp_Twitter.reset_index()

tmp_Twitter

sns.barplot(x="date", y="sentiment_score", color="c", data=tmp_Twitter)

sentiment_Twitter_dict = {'positive': 0, 'negative': 0, 'neutral': 0}
for sentiment in pd_Twitter["sentiment"]:
  if sentiment == "positive":
      sentiment_Twitter_dict['positive'] += 1
  elif sentiment == "neutral":
      sentiment_Twitter_dict['neutral'] += 1
  elif sentiment == "negative":
      sentiment_Twitter_dict['negative'] += 1

sentiment_Twitter = np.array([sentiment_Twitter_dict["positive"], sentiment_Twitter_dict["neutral"], sentiment_Twitter_dict["negative"]])
labels = ["Positive", "Neutral", "Negative"]
colors = sns.color_palette('pastel')[0:5]

plt.pie(sentiment_Twitter, labels=labels, colors=colors, shadow=True, autopct='%.0f%%')
plt.title("Sentiment of tweets of Anteraja")
plt.show()

"""### **B. Google Play Sentiment Analysis**"""

tmp_google_play = pd_google_play.groupby(pd_google_play['at'].dt.day).agg('mean')

tmp_google_play = tmp_google_play.reset_index()

tmp_google_play

sns.barplot(x="at", y="sentiment_score", color="c", data=tmp_google_play)

sentiment_google_play_dict = {'positive' : 0, 'negative' : 0, 'neutral': 0}
for sentiment in pd_google_play["sentiment"]:
  if sentiment == "positive":
      sentiment_google_play_dict['positive'] += 1
  elif sentiment == "neutral":
      sentiment_google_play_dict['neutral'] += 1
  elif sentiment == "negative":
      sentiment_google_play_dict['negative'] += 1

sentiment_google_play = np.array([sentiment_google_play_dict["positive"], sentiment_google_play_dict["neutral"], sentiment_google_play_dict["negative"]])
labels = ["Positive", "Neutral", "Negative"]
colors = sns.color_palette('pastel')[0:5]

plt.pie(sentiment_google_play, labels=labels, colors=colors, shadow=True, autopct='%.0f%%')
plt.title("Sentiment of review of Anteraja on Google Play")
plt.show()