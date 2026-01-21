from django.shortcuts import render


def pricing_view(request):
	return render(request, 'pricing.html')
