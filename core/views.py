from django.shortcuts import render

def landing_view(request):
    return render(request, 'core/landing_page.html')

def login_view(request):
    return render(request, 'core/login.html')

def deployment_hub_view(request):
    # Make sure your actual HTML file is named exactly like this!
    return render(request, 'core/deployment_hub.html') 

def ui_kit_view(request):
    return render(request, 'core/ui_kit.html')