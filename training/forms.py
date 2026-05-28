from django import forms
from .models import Question

class QuestionForm(forms.ModelForm):
    # 1. Logic bach n-jebdu l-catégories unique u n-rttbohom
    def __init__(self, *args, **kwargs):
        super(QuestionForm, self).__init__(*args, **kwargs)
        
        # 1. Jbed ga3 l-catégories (ta7et chkel list dyal strings)
        raw_cats = Question.objects.exclude(categorie__isnull=True).values_list('categorie', flat=True)
        
        # 2. N-qadiwhom: n-7iydo l-fara3at (strip) u n-diro set() bach n-7iydo l-mou3awidin
        # Had l-isla7 k-i-dmen anaka t-7iyd "Phishing " u "Phishing" (m3a espace)
        unique_cats = sorted(list(set(c.strip() for c in raw_cats if c.strip())))
        
        # 3. Qadd l-choices dyalk
        choices = [('', 'Choisir une catégorie...')]
        choices += [(c, c) for c in unique_cats]
        choices += [('AUTRE', '+ Ajouter une nouvelle catégorie')]
        
        # 4. Injecti l-choices f l-field
        self.fields['categorie_select'].choices = choices

    # 2. Field dyal l-choix
    categorie_select = forms.ChoiceField(
        choices=[], # Ghadi i-t-3mmer f __init__
        required=False,
        label="Catégorie existante",
        widget=forms.Select(attrs={
            'class': 'form-control', 
            'style': 'width:100%; background:var(--bg-elevated); border:1px solid var(--border-default); border-radius:var(--radius-md); padding:10px 14px; color:var(--text-primary); outline:none;'
        })
    )

    # 3. Field dyal l-ktiba (ila khtar Autre)
    categorie_nouvelle = forms.CharField(
        required=False,
        label="Ou nouvelle catégorie",
        widget=forms.TextInput(attrs={
            'placeholder': 'Saisir manuellement...', 
            'style': 'display:none; width:100%; background:var(--bg-elevated); border:1px solid var(--border-default); border-radius:var(--radius-md); padding:10px 14px; color:var(--text-primary); margin-top:8px; outline:none;'
        })
    )

    class Meta:
        model = Question
        # Mat-zidi-sh 'categorie' hna hit k-n-qaddouh b l-yedd f la view
        fields = ['texte', 'difficulte', 'poids', 'public', 'reponse_correcte', 'choix_a', 'choix_b', 'choix_c']
        
        widgets = {
            'texte': forms.Textarea(attrs={
                'rows': 3, 
                'placeholder': 'Énoncé de la question...',
                'style': 'width:100%; background:var(--bg-elevated); border:1px solid var(--border-default); border-radius:var(--radius-md); padding:10px 14px; color:var(--text-primary); outline:none;'
            }),
            'difficulte': forms.Select(attrs={
                'style': 'width:100%; background:var(--bg-elevated); border:1px solid var(--border-default); border-radius:var(--radius-md); padding:10px 14px; color:var(--text-primary);'
            }),
            'poids': forms.NumberInput(attrs={
                'style': 'width:100%; background:var(--bg-elevated); border:1px solid var(--border-default); border-radius:var(--radius-md); padding:10px 14px; color:var(--text-primary);'
            }),
            'public': forms.Select(attrs={
                'style': 'width:100%; background:var(--bg-elevated); border:1px solid var(--border-default); border-radius:var(--radius-md); padding:10px 14px; color:var(--text-primary);'
            }),
            'reponse_correcte': forms.TextInput(attrs={
                'placeholder': 'ex: A', 
                'style': 'width:100%; background:var(--bg-elevated); border:1px solid var(--border-default); border-radius:var(--radius-md); padding:10px 14px; color:var(--text-primary);'
            }),
            'choix_a': forms.Textarea(attrs={'rows': 2, 'style': 'width:100%; background:var(--bg-elevated); border:1px solid var(--border-default); border-radius:var(--radius-md); padding:10px 14px; color:var(--text-primary);'}),
            'choix_b': forms.Textarea(attrs={'rows': 2, 'style': 'width:100%; background:var(--bg-elevated); border:1px solid var(--border-default); border-radius:var(--radius-md); padding:10px 14px; color:var(--text-primary);'}),
            'choix_c': forms.Textarea(attrs={'rows': 2, 'style': 'width:100%; background:var(--bg-elevated); border:1px solid var(--border-default); border-radius:var(--radius-md); padding:10px 14px; color:var(--text-primary);'}),
        }