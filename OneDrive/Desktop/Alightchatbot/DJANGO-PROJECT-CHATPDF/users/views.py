from django.shortcuts import render, redirect
from django.urls import reverse_lazy
from django.contrib.auth.views import LoginView, PasswordResetView, PasswordChangeView
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.messages.views import SuccessMessageMixin
from django.views import View
from django.contrib.auth.decorators import login_required, user_passes_test
from .forms import RegisterForm, LoginForm, UpdateUserForm, UpdateProfileForm
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render, redirect, get_object_or_404
from .models import PDFDocument
from django.contrib import messages
import os
from django.http import HttpResponse, FileResponse
import mimetypes
import json
from django.http import JsonResponse
from .models import PDFDocument, ChatSession, ChatMessage
import logging
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.embeddings import CohereEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_community.llms import Cohere
from langchain.memory import ConversationBufferMemory
from langchain.chains import ConversationalRetrievalChain
from langchain_cohere import CohereEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_community.llms import Cohere
from django.contrib.auth import logout
from langchain_community.document_loaders import WebBaseLoader


logger = logging.getLogger(__name__)

COHERE_API_KEY = os.getenv('COHERE_API_KEY')


AVAILABLE_MODELS = {
    'command': 'command',  # Cohere's base model
    'command-light': 'command-light',  # Lighter version
    'command-nightly': 'command-nightly'  # Latest version
}

def home(request):
    return render(request, 'users/home.html')

class RegisterView(View):
    form_class = RegisterForm
    initial = {'key': 'value'}
    template_name = 'users/register.html'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect(to='/')
        return super(RegisterView, self).dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        form = self.form_class(initial=self.initial)
        return render(request, self.template_name, {'form': form})

    def post(self, request, *args, **kwargs):
        form = self.form_class(request.POST)

        if form.is_valid():
            user = form.save()
            
            # Save designation to profile
            user.profile.team_name = request.POST.get('team_name', '')

            designation = request.POST.get('designation')
            user.profile.designation = designation
            user.profile.save()

            username = form.cleaned_data.get('username')
            messages.success(request, f'Account created for {username}')
            return redirect(to='login')

        return render(request, self.template_name, {'form': form})


# Class based view that extends from the built in login view to add a remember me functionality
class CustomLoginView(LoginView):
    template_name = 'users/login.html'
    redirect_authenticated_user = True
    
    def get_success_url(self):
        return reverse_lazy('dashboard')
    
   


    def form_valid(self, form):
        remember_me = form.cleaned_data.get('remember_me')

        if not remember_me:
            # set session expiry to 0 seconds. So it will automatically close the session after the browser is closed.
            self.request.session.set_expiry(0)

            # Set session as modified to force data updates/cookie to be saved.
            self.request.session.modified = True

        # else browser session will be as long as the session cookie time "SESSION_COOKIE_AGE" defined in settings.py
        return super(CustomLoginView, self).form_valid(form)


class ResetPasswordView(SuccessMessageMixin, PasswordResetView):
    template_name = 'users/password_reset.html'
    email_template_name = 'users/password_reset_email.html'
    subject_template_name = 'users/password_reset_subject'
    success_message = "We've emailed you instructions for setting your password, " \
                      "if an account exists with the email you entered. You should receive them shortly." \
                      " If you don't receive an email, " \
                      "please make sure you've entered the address you registered with, and check your spam folder."
    success_url = reverse_lazy('users-home')


class ChangePasswordView(SuccessMessageMixin, PasswordChangeView):
    template_name = 'users/change_password.html'
    success_message = "Successfully Changed Your Password"
    success_url = reverse_lazy('users-home')


def read_pdf_content(file_path):
    """Read content from PDF file with better error handling"""
    try:
        import PyPDF2
        
        with open(file_path, 'rb') as file:
            # Create PDF reader object
            pdf_reader = PyPDF2.PdfReader(file)
            
            # Extract text from all pages
            text = ""
            for page in pdf_reader.pages:
                try:
                    text += page.extract_text() + "\n\n"
                except Exception as e:
                    logger.error(f"Error extracting text from page: {str(e)}")
                    continue
                    
            return text.strip()
    except Exception as e:
        logger.error(f"Error reading PDF file {file_path}: {str(e)}")
        raise ValueError(f"Could not read PDF file: {str(e)}")

def extract_document_text(document):
    """Extract text from document based on file type"""
    file_path = document.file.path
    file_ext = os.path.splitext(file_path)[1].lower()
    
    if file_ext == '.pdf':
        return read_pdf_content(file_path)
    elif file_ext in ['.docx', '.doc']:
        # Add support for Word documents if needed
        raise ValueError("Word document support not implemented yet")
    elif file_ext == '.txt':
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    else:
        raise ValueError(f"Unsupported file type: {file_ext}")
    

def initialize_chat_components(documents):
    try:
        # Extract text from documents
        document_texts = []
        document_metadatas = []

        for doc in documents:
            try:
                text = extract_document_text(doc)
                if text:
                    text_splitter = RecursiveCharacterTextSplitter(
                        chunk_size=500,
                        chunk_overlap=50,
                        separators=["\n\n", "\n", ".", "!", "?"]
                    )
                    chunks = text_splitter.split_text(text)
                    document_texts.extend(chunks)
                    document_metadatas.extend([{
                        "source": f"chunk_{i}",
                        "doc_title": doc.title,
                        "doc_id": doc.id
                    } for i in range(len(chunks))])

            except Exception as e:
                logger.error(f"Error processing document {doc.id}: {str(e)}")
                continue

        if not document_texts:
            raise ValueError("No text could be extracted from documents")

        embeddings = CohereEmbeddings(
            cohere_api_key=COHERE_API_KEY,
            model="embed-english-v3.0"
        )

        vector_store = FAISS.from_texts(
            texts=document_texts,
            embedding=embeddings,
            metadatas=document_metadatas
        )

        llm = Cohere(
            cohere_api_key=COHERE_API_KEY,
            model="command",
            temperature=0.7,
            max_tokens=2048,
            presence_penalty=0.6,
            frequency_penalty=0.3
        )

        memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True,
            output_key="answer"
        )

        chain = ConversationalRetrievalChain.from_llm(
            llm=llm,
            retriever=vector_store.as_retriever(search_kwargs={"k": 3}),
            memory=memory,
            return_source_documents=True,
            verbose=True
        )

        return chain

    except Exception as e:
        logger.error(f"Error in initialize_chat_components: {str(e)}")
        raise


@login_required
def initialize_chat(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            document_ids = data.get('documents', [])
            model = data.get('model', 'command')

            documents = PDFDocument.objects.filter(
                id__in=document_ids,
                team_name=request.user.profile.team_name
            )

            if not documents:
                return JsonResponse({
                    'status': 'error',
                    'message': 'No valid documents found'
                })

            conversation_chain = initialize_chat_components(documents)

            chat_session = ChatSession.objects.create(
                user=request.user,
                model_name=model,
            )
            chat_session.documents.add(*documents)

            request.session[f'chat_session_{chat_session.id}'] = {
                'document_ids': list(documents.values_list('id', flat=True)),
                'model_name': model
            }

            return JsonResponse({
                'status': 'success',
                'session_id': chat_session.id
            })

        except json.JSONDecodeError as e:
            logger.error(f"Error initializing chat: {str(e)}")
            return JsonResponse({
                'status': 'error',
                'message': 'Invalid JSON request'
            })
        except Exception as e:
            logger.error(f"Error initializing chat: {str(e)}")
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            })

    return JsonResponse({
        'status': 'error',
        'message': 'Invalid request method'
    })

@login_required
def chat_response(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            message = data.get('message')
            session_id = data.get('session_id')

            if not message or not session_id:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Missing required parameters'
                })

            # Get chat session and verify ownership
            chat_session = get_object_or_404(ChatSession, 
                id=session_id, 
                user=request.user
            )

            chat_session_data = request.session.get(f'chat_session_{session_id}')
            if not chat_session_data:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Chat session expired. Please start a new chat.'
                })

            documents = PDFDocument.objects.filter(
                id__in=chat_session_data['document_ids'],
                team_name=request.user.profile.team_name
            )

            conversation_chain = initialize_chat_components(documents)

            # Get response with timeout handling
            try:
                response = conversation_chain({
                    "question": message
                })
            except Exception as e:
                logger.error(f"Error getting response: {str(e)}")
                return JsonResponse({
                    'status': 'error',
                    'message': 'Error processing request. Please try again.'
                })

            # Save messages to database
            ChatMessage.objects.create(
                session=chat_session,
                content=message,
                is_bot=True
            )

            bot_message = ChatMessage.objects.create(
                session=chat_session,
                content=response['answer'],
                is_bot=False
            )

            # Add source documents if available
            if 'source_documents' in response:
                for doc in response['source_documents']:
                    if 'doc_id' in doc.metadata:
                        bot_message.relevant_docs.add(doc.metadata['doc_id'])

            return JsonResponse({
                'status': 'success',
                'response': response['answer']
            })

        except Exception as e:
            logger.error(f"Error in chat_response: {str(e)}")
            return JsonResponse({
                'status': 'error',
                'message': 'An error occurred. Please try again.'
            })

    return JsonResponse({
        'status': 'error',
        'message': 'Invalid request method'
    })


@login_required
def profile(request):
    if request.method == 'POST':
        user_form = UpdateUserForm(request.POST, instance=request.user)
        profile_form = UpdateProfileForm(request.POST, request.FILES, instance=request.user.profile)

        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()

            if request.is_ajax():  # Check if the request is AJAX
                return JsonResponse({'status': 'success', 'message': 'Your profile is updated successfully'})
            else:
                messages.success(request, 'Your profile is updated successfully')
                return redirect(to='users-profile')
    else:
        user_form = UpdateUserForm(instance=request.user)
        profile_form = UpdateProfileForm(instance=request.user.profile)

    return render(request, 'users/profile.html', {'user_form': user_form, 'profile_form': profile_form})




@login_required
def dashboard(request):
    return render(request, 'users/dashboard.html')

def is_senior_level(user):
    return hasattr(user, 'profile') and user.profile.designation == "Senior level"

def get_vectorstore_from_documents(documents):
    try:
        # Extract text from documents
        document_texts = []
        document_metadatas = []

        for doc in documents:
            try:
                text = extract_document_text(doc)
                if text:
                    text_splitter = RecursiveCharacterTextSplitter(
                        chunk_size=500,
                        chunk_overlap=50,
                        separators=["\n\n", "\n", ".", "!", "?"]
                    )
                    chunks = text_splitter.split_text(text)
                    document_texts.extend(chunks)
                    document_metadatas.extend([{
                        "source": f"chunk_{i}",
                        "doc_title": doc.title,
                        "doc_id": doc.id
                    } for i in range(len(chunks))])

            except Exception as e:
                logger.error(f"Error processing document {doc.id}: {str(e)}")
                continue

        if not document_texts:
            raise ValueError("No text could be extracted from documents")

        embeddings = CohereEmbeddings(
            cohere_api_key=COHERE_API_KEY,
            model="embed-english-v3.0"
        )

        vector_store = FAISS.from_texts(
            texts=document_texts,
            embedding=embeddings,
            metadatas=document_metadatas
        )

        return vector_store

    except Exception as e:
        logger.error(f"Error in get_vectorstore_from_documents: {str(e)}")
        raise
def get_context_retriever_chain(vector_store):
    # Use Cohere as the LLM model
    llm = Cohere(
        cohere_api_key=COHERE_API_KEY,
        model="command",
        temperature=0.7,
        max_tokens=2048,
        presence_penalty=0.6,
        frequency_penalty=0.3
    )

    # Create a retriever for the vector store
    retriever = vector_store.as_retriever()

    # Create a conversation buffer memory
    memory = ConversationBufferMemory(
        memory_key="chat_history",
        return_messages=True,
        output_key="answer"
    )

    # Define the retrieval chain
    chain = ConversationalRetrievalChain.from_llm(
        llm=llm,
        retriever=retriever,
        memory=memory,
        return_source_documents=True,
        verbose=True
    )

    return chain
@login_required
def alight_chatbot(request):
    if request.method == 'POST':
        user_input = request.POST.get('user_input')
        if user_input:
            try:
                # Initialize the web loader and retrieval chain
                website_url = "https://www.alight.com/about/leadership"
                loader = WebBaseLoader(website_url)
                document = loader.load()

                text_splitter = RecursiveCharacterTextSplitter()
                document_chunks = text_splitter.split_documents(document)

                embeddings = CohereEmbeddings(
                    cohere_api_key=COHERE_API_KEY,
                    model="embed-english-v3.0"
                )
                vector_store = FAISS.from_documents(document_chunks, embeddings)
                retrieval_chain = get_context_retriever_chain(vector_store)

                # Get response from the chain
                response = retrieval_chain({"question": user_input})
                chat_message = response['answer']

                # Return just the message content for AJAX handling
                return render(request, 'users/chat_message.html', {
                    'chat_message': chat_message
                })
            except Exception as e:
                logger.error(f"Error processing user input: {str(e)}")
                return render(request, 'users/chat_message.html', {
                    'error_message': 'Error processing your request. Please try again.'
                })

    # Initial page load
    return render(request, 'users/alight_chatbot.html')



def save_chat_message(user, user_input, bot_response, source_documents):
    # Implementation left for the reader
    pass




@login_required
def download_document(request, doc_id):
    try:
        # Get document and check team access
        document = get_object_or_404(PDFDocument, id=doc_id)
        
        # Check if user has access to this document
        if document.team_name != request.user.profile.team_name:
            messages.error(request, 'You do not have permission to access this document.')
            return redirect('document_management')
            
        file_path = document.file.path
        
        if os.path.exists(file_path):
            with open(file_path, 'rb') as fh:
                response = HttpResponse(fh.read(), content_type='application/force-download')
                response['Content-Disposition'] = f'attachment; filename="{os.path.basename(document.file.name)}"'
                return response
                
        messages.error(request, 'File not found')
        return redirect('document_management')
        
    except Exception as e:
        messages.error(request, f'Error downloading document: {str(e)}')
        return redirect('document_management')

@login_required
def preview_document(request, doc_id):
    try:
        # Get document and check team access
        document = get_object_or_404(PDFDocument, id=doc_id)
        
        # Check if user has access to this document
        if document.team_name != request.user.profile.team_name:
            messages.error(request, 'You do not have permission to access this document.')
            return redirect('document_management')
            
        file_path = document.file.path
        
        if os.path.exists(file_path):
            content_type, _ = mimetypes.guess_type(document.file.name)
            with open(file_path, 'rb') as fh:
                response = HttpResponse(fh.read(), content_type=content_type or 'application/octet-stream')
                response['Content-Disposition'] = f'inline; filename="{os.path.basename(document.file.name)}"'
                return response
                
        messages.error(request, 'File not found')
        return redirect('document_management')
        
    except Exception as e:
        messages.error(request, f'Error previewing document: {str(e)}')
        return redirect('document_management')
    
@login_required
def document_management(request):
    # Get user's team name
    user_team = request.user.profile.team_name
    
    # Filter documents based on team access
    documents = PDFDocument.objects.filter(team_name=user_team)
    
    return render(request, 'users/document_management.html', {
        'documents': documents,
        'is_senior': request.user.profile.designation == "Senior level",
        'user_team': user_team
    })

@login_required
def upload_document(request):
    if request.user.profile.designation != "Senior level":
        messages.error(request, 'Only senior level employees can upload documents.')
        return redirect('document_management')
    
    if request.method == 'POST':
        title = request.POST.get('title')
        document = request.FILES.get('document')
        
        if not title:
            title = os.path.splitext(document.name)[0]
        
        try:
            header = document.read(4)
            document.seek(0)
            
            if not (header.startswith(b'%PDF') or header.startswith(b'PK')):
                messages.error(request, 'Please upload only PDF or DOCX files.')
                return redirect('document_management')
            
            # Create document with team information
            PDFDocument.objects.create(
                user=request.user,
                title=title,
                file=document,
                team_name=request.user.profile.team_name  # Add team name
            )
            messages.success(request, 'Document uploaded successfully!')
            
        except Exception as e:
            messages.error(request, f'Error uploading document: {str(e)}')
            
    return redirect('document_management')


@login_required
def delete_document(request, doc_id):
    if request.user.profile.designation != "Senior level":
        messages.error(request, 'Only senior level employees can delete documents.')
        return redirect('document_management')
       
    try:
        document = get_object_or_404(PDFDocument, id=doc_id, team_name=request.user.profile.team_name)
        document.delete()
        messages.success(request, 'Document deleted successfully!')
    except Exception as e:
        messages.error(request, f'Error deleting document: {str(e)}')
    
    return redirect('document_management')





@login_required
def download_document(request, doc_id):
    try:
        document = get_object_or_404(PDFDocument, id=doc_id)
        
        # Check team access
        if request.user.profile.team_name != document.team_name:
            messages.error(request, 'You do not have permission to download this document.')
            return redirect('document_management')

        file_path = document.file.path
        if os.path.exists(file_path):
            with open(file_path, 'rb') as fh:
                response = HttpResponse(fh.read(), content_type='application/force-download')
                response['Content-Disposition'] = f'attachment; filename="{os.path.basename(document.file.name)}"'
                return response
        
        messages.error(request, 'File not found')
        
    except Exception as e:
        messages.error(request, f'Error downloading document: {str(e)}')
        
    return redirect('document_management')

@login_required
def preview_document(request, doc_id):
    document = get_object_or_404(PDFDocument, id=doc_id)
    file_path = document.file.path
    if os.path.exists(file_path):
        with open(file_path, 'rb') as fh:
            response = HttpResponse(fh.read(), content_type=get_content_type(document.file.name))
            return response
    raise Http404

def get_content_type(filename):
    # Add content type mapping based on file extension
    content_types = {
        '.pdf': 'application/pdf',
        '.doc': 'application/msword',
        '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        '.txt': 'text/plain',
        # Add more as needed
    }
    ext = os.path.splitext(filename)[1].lower()
    return content_types.get(ext, 'application/octet-stream')

@login_required
def document_chat(request):
    # Filter documents based on team access
    user_team = request.user.profile.team_name
    documents = PDFDocument.objects.filter(
        team_name=user_team,
        user__profile__designation='Senior level'
    ).order_by('-uploaded_at')
    
    context = {
        'documents': documents,
        'team_name': user_team
    }
    return render(request, 'users/document_chat.html', context)


def validate_pdf(file_obj):
    """Validate if file is a genuine PDF"""
    try:
        # Save first few bytes of the file
        file_obj.seek(0)
        header = file_obj.read(4)
        file_obj.seek(0)  # Reset file pointer
        
        # Check if it's a real PDF (should start with %PDF)
        if not header.startswith(b'%PDF'):
            # Check if it's a zip file (starts with PK)
            if header.startswith(b'PK'):
                raise ValueError("File appears to be a DOCX/ZIP file renamed as PDF")
            raise ValueError("Invalid PDF file format")
            
        return True
    except Exception as e:
        raise ValueError(f"PDF validation failed: {str(e)}")







@login_required
def document_list(request):
    documents = PDFDocument.objects.filter(user=request.user).values(
        'id', 'title', 'uploaded_at'
    )
    return JsonResponse(list(documents), safe=False)



def custom_logout(request):
    # Perform logout
    logout(request)

    # Redirect the user to the logout page
    return redirect('logout_page')

def logout_page(request):
    return render(request, 'users/logout.html')