from django.db import models
from django.contrib.auth.models import User
from PIL import Image
import os
 
 
# Extending User Model Using a One-To-One Link
# users/models.py
class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    avatar = models.ImageField(upload_to='profile_images')
    bio = models.TextField()
    team_name = models.CharField(max_length=100, default='')  # Add this line
    designation = models.CharField(max_length=100, default='')
 
    def __str__(self):
        return self.user.username
 
   
 
class PDFDocument(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=255, unique=True, default='Untitled Document')
    file = models.FileField(upload_to='pdfs/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    team_name = models.CharField(max_length=100, default='')
    processed = models.BooleanField(default=False)
    vector_store_path = models.CharField(max_length=500, null=True, blank=True)
    embedding_path = models.CharField(max_length=500, null=True, blank=True)
    content_text = models.TextField(null=True, blank=True)
 
    def __str__(self):
        return f"{self.title} - {self.user.username}"
 
    def delete(self, *args, **kwargs):
        # Delete the physical file
        if self.file:
            if os.path.isfile(self.file.path):
                os.remove(self.file.path)
       
        # Delete embeddings if they exist
        if self.embedding_path and os.path.exists(self.embedding_path):
            try:
                os.remove(self.embedding_path)
            except Exception as e:
                print(f"Error deleting embedding: {e}")
       
        # Call the parent class's delete method
        super().delete(*args, **kwargs)
       
       
class ChatSession(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    documents = models.ManyToManyField(PDFDocument)
    created_at = models.DateTimeField(auto_now_add=True)
    model_name = models.CharField(max_length=100, default='llama3-8b-8192')
   
    def __str__(self):
        return f"Chat session for {self.user.username}"
 
class ChatMessage(models.Model):
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE)
    content = models.TextField()
    is_bot = models.BooleanField(default=False)
    timestamp = models.DateTimeField(auto_now_add=True)
    relevant_docs = models.ManyToManyField(PDFDocument, blank=True)
    confidence_score = models.FloatField(default=0.0)
   
    class Meta:
        ordering = ['timestamp']
   
    def __str__(self):
        return f"{'Bot' if self.is_bot else 'User'} message in {self.session}"