"""Deterministic Arabic currency wording; Decimal rounding, never binary floats."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

ONES = ('صفر','واحد','اثنان','ثلاثة','أربعة','خمسة','ستة','سبعة','ثمانية','تسعة','عشرة','أحد عشر','اثنا عشر','ثلاثة عشر','أربعة عشر','خمسة عشر','ستة عشر','سبعة عشر','ثمانية عشر','تسعة عشر')
TENS = ('','','عشرون','ثلاثون','أربعون','خمسون','ستون','سبعون','ثمانون','تسعون')
HUNDREDS = ('','مائة','مائتان','ثلاثمائة','أربعمائة','خمسمائة','ستمائة','سبعمائة','ثمانمائة','تسعمائة')
CURRENCIES = {
 'SAR': (('ريال سعودي','ريالان سعوديان','ريالات سعودية'),('هللة','هللتان','هللات'),2),
 'USD': (('دولار أمريكي','دولاران أمريكيان','دولارات أمريكية'),('سنت','سنتان','سنتات'),2),
 'AED': (('درهم إماراتي','درهمان إماراتيان','دراهم إماراتية'),('فلس','فلسان','فلوس'),2),
 'KWD': (('دينار كويتي','ديناران كويتيان','دنانير كويتية'),('فلس','فلسان','فلوس'),3),
 'BHD': (('دينار بحريني','ديناران بحرينيان','دنانير بحرينية'),('فلس','فلسان','فلوس'),3),
}
FEMININE = ('صفر','واحدة','اثنتان','ثلاث','أربع','خمس','ست','سبع','ثمان','تسع','عشر','إحدى عشرة','اثنتا عشرة','ثلاث عشرة','أربع عشرة','خمس عشرة','ست عشرة','سبع عشرة','ثماني عشرة','تسع عشرة')
def under1000(n, feminine=False):
 words=FEMININE if feminine else ONES
 parts=[]
 if n>=100: parts.append(HUNDREDS[n//100]); n%=100
 if n:
  if n<20: parts.append(words[n])
  else: parts.append((' و'.join([words[n%10],TENS[n//10]]) if n%10 else TENS[n//10]))
 return ' و'.join(parts)
def number(n,feminine=False):
 if n==0:return ONES[0]
 if not 0<=n<10**12:raise ValueError('Amount outside supported range')
 parts=[]
 for value,one,two,few in ((10**9,'مليار','ملياران','مليارات'),(10**6,'مليون','مليونان','ملايين'),(1000,'ألف','ألفان','آلاف')):
  q,n=divmod(n,value)
  if q:parts.append(one if q==1 else two if q==2 else under1000(q)+' '+(few if 3<=q<=10 else one))
 if n:parts.append(under1000(n,feminine))
 return ' و'.join(parts)
def named(n,forms):
 if n==1:return forms[0]+' واحد' if forms[0] not in ('هللة',) else 'هللة واحدة'
 if n==2:return forms[1]
 return number(n,forms[0]=='هللة')+' '+(forms[2] if 3<=n%100<=10 else forms[0])
def amount_words(value,currency='SAR'):
 code=str(currency or 'SAR').upper()
 forms,minor,precision=CURRENCIES.get(code,((code,code,code),('جزء من العملة','جزآن من العملة','أجزاء من العملة'),2))
 try:amount=Decimal(str(value or 0))
 except InvalidOperation:raise ValueError('Invalid amount') from None
 if not amount.is_finite():raise ValueError('Invalid amount')
 negative=amount<0; amount=abs(amount).quantize(Decimal(1).scaleb(-precision),rounding=ROUND_HALF_UP)
 whole=int(amount);fraction=int((amount-whole)*(10**precision))
 text=named(whole,forms)
 if fraction:text+=' و'+named(fraction,minor)
 return 'فقط '+('سالب ' if negative else '')+text+' لا غير'
