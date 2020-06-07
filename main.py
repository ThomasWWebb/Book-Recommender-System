import os
import psycopg2
from flask import Flask, flash, jsonify
from flask import render_template
from flask import request
from flask import redirect
from flask_login import LoginManager, UserMixin, login_required, current_user, login_user, logout_user
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import create_engine
import pandas as  pd
import numpy as np
from scipy.sparse.linalg import svds
import json

app = Flask(__name__)

secretKey = "setValue" #Set secret key
app.config['SECRET_KEY'] = secretKey
#app.config["SQLALCHEMY_DATABASE_URI"] = 
db = SQLAlchemy(app)


login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

##############################################################

@app.route('/signup')
def signup():
    return render_template('signup.html')

@app.route("/signUpAuth", methods=["POST"])
def authSignUp():
    data = request.get_json()
    username = data["username"]
    password = data["password"]
    user = User.query.filter_by(username=username).first()
    if user:
        flash('Email address already exists')
        return jsonify("false")

    newUser = User(username=username, password=password)
    db.session.add(newUser)
    db.session.commit()
    login_user(newUser, remember=True)

    return jsonify("true")

###############################################################


@app.route('/logout')
def logout():
    logout_user()
    return redirect("/login")

@app.route('/login')
def login():
    return render_template('login.html')

@app.route("/loginAuth", methods=["POST"])
def authLogin():
    data = request.get_json()
    username = data["username"]
    password = data["password"]
    user = User.query.filter_by(username=username).first()
    if not user or user.password != password:
        return jsonify("false")
    login_user(user, remember=True)
    return jsonify("true")

############################################################################

@app.route('/', methods=["POST"])
def indexAddRating():
    action = ""
    data = request.get_json()
    bookID = int(data['bookID'])
    rating = Rating(userID=current_user.id, bookID=bookID, bookRating=int(data['bookRating']))
    queryRating = Rating.query.filter_by(userID=current_user.id,bookID=int(data['bookID'])).first()
    if not queryRating:
        action = "new"
        book = Book.query.filter_by(bookID=bookID).first()
        data['title'] = book.title
        db.session.add(rating)
    else:
        action = "update"
        queryRating.bookRating = rating.bookRating
        
    db.session.commit()
    data['action'] = action
    return data

@app.route('/', methods=["GET"])
@login_required
def index():
    ratings = Rating.query.filter_by(userID=current_user.id)
    userRatings = []
    recommendations = []
    if len(ratings.all()) > 0:
        for rat in ratings:
            book = Book.query.filter_by(bookID=rat.bookID).first()
            if book:
                userRatings.append(UserRating(rating=rat, title=book.title))
        if len(userRatings) > 0:
            recommendations = getRecommendations("Any")
    else:
        recommendations = ["Please rate some books to start getting recommendations"]

    books = Book.query.all()
    genres = getGenres(books)
    return render_template('index.html', user=current_user, userRatings=userRatings, books=books, recommendations=recommendations, genres=genres)

@app.route('/recommendations', methods=["POST"])
@login_required
def recommendBooks():
    data = request.get_json()
    genre = data
    ratings = Rating.query.filter_by(userID=current_user.id)
    userRatings = []
    recommendations = []
    if len(ratings.all()) > 0:
        for rat in ratings:
            book = Book.query.filter_by(bookID=rat.bookID).first()
            if book:
                userRatings.append(UserRating(rating=rat, title=book.title))
        if len(userRatings) > 0:
            recommendations = getRecommendations(genre)
    else:
        recommendations = ["Please rate some books to start getting recommendations"]
    if len(recommendations) == 0:
        recommendations = ["You have already read all the books we have stored"]
    return jsonify(recommendations)
    
def getGenres(books):
    genres = ["Any"]
    for book in books:
        if not (book.genre in genres):
            genres.append(book.genre)
    return genres



def getRecommendations(genre):
    cnx = psycopg2.connect(app.config["SQLALCHEMY_DATABASE_URI"])
    bookData = pd.read_sql_query("SELECT * FROM books", cnx)
    userData = pd.read_sql_query("SELECT * FROM ratings", cnx)
    userData = pd.merge(userData, bookData['bookID'], on='bookID')
    predictionsFrame, bookFrame = getPredMatrix(bookData, userData)
    predictions = makeRecommendations(predictionsFrame, current_user.id, bookData, userData,bookFrame)
    recommendations = []
    if genre != "Any":
        for index, row in (predictions).iterrows():
            if row['genre'] == genre:
                recommendations.append(row['title'])
            if len(recommendations) == 9:
                break
    else:
        for index, row in (predictions.head(10)).iterrows():

            recommendations.append(row['title'])
    return recommendations


@app.route("/ratingUpdate", methods=["POST"])
def ratingUpdate():
    data = request.get_json()
    bookID = data["bookID"]
    user = current_user
    bookRating = data["bookRating"]
    queryRating = Rating.query.filter_by(userID=current_user.id,bookID=bookID).first()
    queryRating.bookRating = bookRating
    db.session.commit()
    return "True"

@app.route("/ratingDelete", methods=["POST"])
def ratingDelete():
    data = request.get_json()
    bookID = data["bookID"]
    user = current_user
    rating = Rating.query.filter_by(userID=current_user.id,bookID=bookID).first()
    db.session.delete(rating)
    db.session.commit()
    return "True"

############################################################

@app.route('/books', methods = ["GET"])
@login_required
def books():
    books = Book.query.all()
    return render_template('books.html', user=current_user, books=books)

@app.route('/addBook', methods = ["POST"])
def addBook():
    data = request.get_json()
    book = Book(title=data["title"], genre=data["genre"])
    queryBook = Book.query.filter_by(title=data["title"]).first()
    if not queryBook:
        db.session.add(book)
        db.session.commit()
        data['bookID'] = book.bookID
        data['result'] = "true"
        return data
    else:
        data['result'] = "false"
        return data


@app.route("/bookUpdate", methods=["POST"])
def bookUpdate():
    data = request.get_json()
    newtitle = data["title"]
    newGenre = data["genre"]
    bookID = data["bookID"]
    queryBook = Book.query.filter_by(title=newtitle).first()
    if queryBook:
        return jsonify("false")
    else:
        book = Book.query.filter_by(bookID=bookID).first()
        book.title = newtitle
        book.genre = newGenre
        db.session.commit()
        return jsonify("true")
    
    

@app.route("/bookDelete", methods=["POST"])
def bookDelete():
    data = request.get_json()
    bookID = data["bookID"]
    book = Book.query.filter_by(bookID=bookID).first()
    ratings = Rating.query.filter_by(bookID=bookID)
    if len(ratings.all()) > 0:
        for rating in ratings:
            db.session.delete(rating)
    db.session.delete(book)
    db.session.commit()
    return data

##############################################################

@app.route("/users", methods=["GET"])
@login_required
def users():
    users = User.query.all()
    return render_template("users.html", users=users)

@app.route("/userUpdate", methods=["POST"])
def userUpdate():
    data = request.get_json()
    username = data["username"]
    password = data["password"]
    id = data["id"]
    queryUser = User.query.filter_by(username=username).first()
    if queryUser and str(queryUser.id) != id:
        return jsonify("false")
    else:
        user = User.query.filter_by(id=id).first()
        user.username = username
        user.password = password
        db.session.commit()
        return jsonify("true")

@app.route("/userDelete", methods=["POST"])
def userDelete():
    data = request.get_json()
    id = data["id"]
    user = User.query.filter_by(id=id).first()
    ratings = Rating.query.filter_by(userID=id)
    if len(ratings.all()) > 0:
        for rating in ratings:
            db.session.delete(rating)
    db.session.delete(user)
    db.session.commit()
    return data

##############################################################

@app.route('/profile', methods=["GET"])
@login_required
def profile():
    id = current_user.id
    user = User.query.filter_by(id=id).first()
    return render_template("profile.html", user=user)

@app.route('/updateProfile', methods=['POST'])
def updateProfile():
    data = request.get_json()
    queryUser = User.query.filter_by(username=data['username']).first()
    if queryUser:
        return jsonify("false")
    else:
        user = User.query.filter_by(id=current_user.id).first()
        user.username = data['username']
        user.password = data['password']
        db.session.commit()
        return jsonify("true")

##############################################################

@app.route('/database')
def database():
    '''
    bookData = pd.read_csv("newBooks.csv", header=0, names=["bookID", "genre", "title"])
    for index, row in bookData.iterrows():
        book = Book(bookID=row['bookID'], genre=row['genre'], title=row['title'])
        queryUser = User.query.filter_by(id=username, username=username).first()
        db.session.add(book)
        db.session.commit()

    userData = pd.read_csv('ratings.csv', header=0, names=["userID", "bookID", "bookRating"])
    subUserData = userData[:10000]
    for index, row in subUserData.iterrows():
        rating = Rating(userID=row['userID'], bookID=row['bookID'], bookRating=row['bookRating'])
        db.session.add(rating)
        db.session.commit()

    userData = pd.read_csv('ratings.csv', header=0, names=["userID", "bookID", "bookRating"])
    subUserData = userData[:10000]
    prevUserID = -1
    for index, row in subUserData.iterrows():
        username = row['userID']
        username = str(username)
        if username != prevUserID:
            queryUser = User.query.filter_by(id=username, username=username).first()
            if not queryUser:
                user = User(id=int(username),username=str(username), password="password")
                db.session.add(user)
                db.session.commit()
    '''
    return redirect("/")


#######################################################################


class Book(db.Model):
    __tablename__ = 'books'
    bookID = db.Column(db.Integer, primary_key=True)
    genre = db.Column(db.String(200), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    

    def __repr__(self):
        return "<Title: {}>".format(self.title)

class Rating(db.Model):
    __tablename__ = 'ratings'
    userID = db.Column(db.Integer, primary_key=True)
    bookID = db.Column(db.Integer, primary_key=True)
    bookRating = db.Column(db.Integer, nullable=False)

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100))
    password = db.Column(db.String(100))

class UserRating():
    def __init__(self, rating, title):
            self.rating = rating
            self.title = title

db.create_all()

def getPredMatrix(bookData, userData):
    userData['bookID'] = pd.to_numeric(userData['bookID'])
    userData['userID'] = pd.to_numeric(userData['userID'])
    userData['bookRating'] = pd.to_numeric(userData['bookRating'])
    bookFrame = userData.pivot_table(index='userID', columns='bookID', values='bookRating').fillna(0)
    bookMatrix = bookFrame.as_matrix()
    userRatingsMean = np.mean(bookMatrix, axis = 1)
    normalisedBookMatrix = bookMatrix - userRatingsMean.reshape(-1, 1)
    maxK = min(normalisedBookMatrix.shape) - 1
    k = 50
    if maxK < k:
        k = maxK
    U, sigma, Vt = svds(normalisedBookMatrix, k )
    sigma = np.diag(sigma)
    allPredictions = np.dot(np.dot(U, sigma), Vt) + userRatingsMean.reshape(-1, 1)
    predictionsFrame = pd.DataFrame(allPredictions, columns = bookFrame.columns)
    return predictionsFrame, bookFrame

def makeRecommendations(predictionsFrame, userID, bookData, userData, bookFrame,):
    
    userPos = bookFrame.index.get_loc(userID)
    sortedPredictions = predictionsFrame.iloc[userPos].sort_values(ascending=False)
    user_data = userData[userData.userID == (userID)]
    bookData['bookID'] = pd.to_numeric(bookData['bookID'])
    user_data['bookID'] = pd.to_numeric(user_data['bookID'])
    calcUserResults = (user_data.merge(bookData, how = 'left', on = 'bookID').sort_values(['bookRating'], ascending=False))
    recommendations = (bookData[~bookData['bookID'].isin(calcUserResults['bookID'])].
         merge(pd.DataFrame(sortedPredictions).reset_index(), how = 'left', on = 'bookID').
         rename(columns = {userPos: 'Predictions'}).
         sort_values('Predictions', ascending = False))

    return recommendations
