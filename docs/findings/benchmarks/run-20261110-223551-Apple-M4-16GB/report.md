# Real talks by Turkish speakers, scored against human captions

MacBook Air (Apple M4, 16 GB). WER = word error rate against the human captions (lower is better); live = the app's streaming recognition, offline = the same model on 28 s windows. A few words at the edges of each excerpt may not line up with the captions (about 1-2 points).

| Speech model | Talk | WER live | WER offline | ms per pass |
|---|---|---|---|---|
| gemini (input transcript) | Ahmet Turer, TEDxMETUAnkara: Turkish engineering talk (human TR captions) | 13.3% | - | - |
| gemini (input transcript) | Saffet Emre Tonguc, TEDxIstanbul: Turkish talk (human TR captions) | 15.0% | - | - |

| Gemini | Talk | chrF vs human Turkish | delay after source text (p50) | last text after audio end |
|---|---|---|---|---|
| gemini | Ahmet Turer, TEDxMETUAnkara: Turkish engineering talk (human TR captions) | - | 0.2589997499999299 s | -0.19 s |
| gemini | Saffet Emre Tonguc, TEDxIstanbul: Turkish talk (human TR captions) | - | 0.27308958299909136 s | -0.09 s |
| gemini | Ayse Bilge Gunduz, WomenTech: English by a Turkey-based developer | - | 0.22870562499883818 s | -0.13 s |
| gemini | Gonul Ayci, PyCon DE lightning talk: English by a Turkey-based developer | - | 0.30663937499775784 s | -1.87 s |
| gemini | Python Saati #85 (pyistanbul), from 18:00: Turkish tech talk | - | 0.225140583999746 s | -0.34 s |
| gemini | Python Saati #102 (pyistanbul), Celery: regular Turkish tech presentation | - | 0.2607629160011129 s | -3.04 s |

## Subtitles: what was heard live (best speech model) and each translation

### Ahmet Turer, TEDxMETUAnkara: Turkish engineering talk (human TR captions)

Gemini Live Translate (its own sentences; source = its input transcript):

- [2:03] **İlk yaptığınız şey yüzünüzü yıkamak. Musluğu**
  - `gemini`: The first thing you do is wash your face.
- [2:04] **açtığınızda akan su borulardan inşaat mühendislerinin sayesinde geliyor.**
  - `gemini`: When you turn on the faucet, the water flowing through the pipes is thanks to civil engineers.
- [2:09] **İnşaat mühendislerinin yaptığı barajlardan geliyor.**
  - `gemini`: The work of civil engineers on dams is where it comes from.
- [2:12] **Daha sonra lavabodan giden kirli atık su yine kanalizasyon sistemiyle bizim sayemizde**
  - `gemini`: Then the dirty water going down the sink also goes through the sewage system, which is thanks to us.
- [2:18] **Daha sonra arabanıza bindiniz ya da toplu taşıma.**
  - `gemini`: Then you get in your car or take public transportation.
- [2:22] **İş yerinize giderken geçtiğiniz yolları inşaat mühendisleri yapıyor.**
  - `gemini`: On your way to work, the roads you pass are built by civil engineers.
- [2:26] **Köprüler, tüneller hava limanları, kıyı liman ve iş yerinde çalıştığınız tabii ki ofisler sonra tekrar evinize gelip rahat yatağınızda yattığınız evler**
  - `gemini`: Bridges, tunnels, airports, coastal ports, and your workplace where you work, of course, the offices then again you come home and lie down in your comfortable bed and the houses
- [2:39] **elbette inşaat mühendisleri tarafından.**
  - `gemini`: are of course built by civil engineers.
- [2:41] **Ve işin ilginç tarafı inşaat mühendisliği insanlık kadar eski bir**
  - `gemini`: And the interesting part is that civil engineering is as old as humanity.
- [2:47] **meslek. Eee eee insanlığın ilk yerleşimleri yine Anadolu'da. Bu da**
  - `gemini`: Uh, uh, humanity's first settlements were also in Anatolia.
- [2:53] **büyük bir rastlantı. Göbekli**
  - `gemini`: This is a big coincidence.
- [2:56] **Tepe bundan 12 bin yıl önce ilk inşaatın başladığı yer ve bundan sonra belki muhtemelen en eski inşaat planı da milattan önce 1800'lü yıllara geliyor.**
  - `gemini`: Göbekli Tepe was built 12,000 years ago, the first construction site, and after that, maybe probably the oldest construction plan is also from before 1800 BC.
- [3:08] **Eee aynı yıllarda yaşayan Babil kralı Hammurabi'nin sorumluluk ve vicdan üzerine yasaları var.**
  - `gemini`: Uh, the Babylonians living in the same years, King Hammurabi had a responsibility and conscience about laws.
- [3:15] **Bunun 229. maddesi inşa ettiği bina yıkılıp sahibini öldürürse inşaatı yapan da öldürülür.**
  - `gemini`: This is the 229th article that if a building he built collapses and kills the owner, the builder is also killed.
- [3:23] **Eee Bir sonraki 230. madde eğer bina ev sahibinin çocuğunu öldürürse inşaatı yapanın çocuğu da**
  - `gemini`: Uh, The next 230th article is that if the building kills the owner's child, the builder's child is also killed.
- [3:33] **öldürülür. Eee gördüğünüz gibi sorumluluklarla iç içe bir meslek. Eee**
  - `gemini`: Uh, as you can see, responsibility is an integral part of the profession.
- [3:38] **eee eee Maslow'un ihtiyaçlar hiyerarşisinde arkamda gördüğünüz gibi bir piramit var ve bu piramitin aşağıdaki en geniş tabanlı kısmı bizim en**
  - `gemini`: Uh, uh, Maslow's hierarchy of needs In the hierarchy you see behind me, there is a pyramid,
- [3:49] **çok ihtiyacımız**
  - `gemini`: and the widest part at the bottom of this pyramid is our most basic need.
- [3:51] **olan şey. Bunların başında da**
  - `gemini`: This is also at the top of the list.
- [3:53] **temel fizyolojik ihtiyaçlar barınma, su, ulaşım, güvenlik gibi konular**
  - `gemini`: Basic physiological needs are shelter, water, transportation, and security.
- [3:58] **geliyor ki inşaat mühendisliği bu konularla ilgili çalışmalar**
  - `gemini`: So, civil engineering is directly related to these issues.
- [4:03] **yapıyor. Eee muhtemelen bilmediğiniz bir gerçek var.**
  - `gemini`: Uh, probably something you don't know.
- [4:06] **Türkiye inşaat sektöründe son 10 yıldır dünya ikincisi.**
  - `gemini`: Turkey is the construction sector in the last 10 years, the world is second.
- [4:12] **Birincisi Çin.**
  - `gemini`: The first is China.
- [4:13] **Eee bu benim için bayağı etkileyici bir istatistik.**
  - `gemini`: Uh, this is quite an impressive statistic for me.
- [4:17] **Bizim ülkemizdeki müteahhitler dünyadaki en büyük 250 müteahhit arasında 44 tanesi Türk firması. Ve**
  - `gemini`: Our country's contractors are the biggest in the world's top 250 contractors, and 44 of them are Turkish firms.
- [4:26] **126 farklı ülkede 48 yılda 10.000 projenin toplam maliyeti 400 milyar dolardan fazla.**
  - `gemini`: And in 126 different countries, in 48 years, a total cost of 400 billion dollars.
- [4:32] **Ayrıca inşaat sektörü her dönemde eee ülke ekonomisinin lokomotifi pozisyonunda. O**
  - `gemini`: Also, the construction sector in every period uh the country's economy's locomotive position.
- [4:40] **zaman şu soruyu sorabiliriz kendimize.**
  - `gemini`: So, I can ask ourselves this question.
- [4:42] **Nasıl oluyor da Türkiye'de depremlerde bunca kayıplar yaşanabiliyor?**
  - `gemini`: How is it that in Turkey in earthquakes so many losses can occur?
- [4:48] **Eee bunun cevabı belki de bu fotoğrafta gizli.**
  - `gemini`: Uh, the answer to this is perhaps hidden in this photo.
- [4:52] **Acaba aranızda cevabı**
  - `gemini`: I wonder if anyone among you can see the answer?
- [4:56] **görebilen var mı? Eee eee bu cevaplara eee gelmeden önce belki de şapkamızı çıkartıp önümüze koyup ciddi ciddi düşünmemiz**
  - `gemini`: Uh, uh, to these answers, uh before getting to them, maybe we should take off our hats and put them in front of us and seriously think about it.
- [5:07] **lazım. Nerede hata yapıyoruz?**
  - `gemini`: Where are we making a mistake?
- [5:12] **Eee sebeplere geleceğim ama size birkaç bilgi vermek istiyorum.**
  - `gemini`: Uh, I'll get to the reasons but I want to give you some information first.
- [5:17] **Mesela 2004 yılında bir Kurban Bayramı akşamı eee hiçbir deprem olmadan yıkılan Zümrüt apartmanını hepiniz hatırlıyorsunuzdur.**
  - `gemini`: For example, in 2004, on the evening of Eid al-Adha, uh, without any earthquake happening, the Zümrüt apartment building that you all remember happened.
- [5:27] **Kendi ağırlığı altında**
  - `gemini`: It collapsed under its own weight.
- [5:29] **yıkıldı. Hala davası devam**
  - `gemini`: It's still in court.
- [5:31] **ediyor. Kolon kesildiğine dair bir bilgi var ama emin**
  - `gemini`: The columns were cut, there's information about that, but we're not sure.
- [5:36] **değiliz. Eğer günümüze gelirsek Elazığ depremi geçtiğimiz günlerde oldu.**
  - `gemini`: If we come to the present, in the Elazığ earthquake, which happened recently.

### Saffet Emre Tonguc, TEDxIstanbul: Turkish talk (human TR captions)

Gemini Live Translate (its own sentences; source = its input transcript):

- [2:03] **diye sorarlarsa Çamlıca Güzeltepe Fikir Tepe garet Tepe falan demeyin. Hepsi bunların tarihi yarımadada.**
  - `gemini`: If they ask, "Is it Çamlıca Güzeltepe Fikir Tepe or Garet Tepe or something like that, don't say that.
- [2:10] **yer alıyor ve Osmanlılar ne yapmış? 7 tepeye birbirinden güzel**
  - `gemini`: They are all in the historical peninsula, and what did the Ottomans do?
- [2:14] **camiler yapmış. İsterseniz bunları bir sayarak başlayalım işe.**
  - `gemini`: They built beautiful mosques on the seven hills.
- [2:16] **Birinci tepede**
  - `gemini`: Let's start by counting them.
- [2:18] **Sultan Ahmet Camii var. 6 minaresiyle çok görkemli ve tam karşısında da bana göre dünya mimarlık tarihinin en olağanüstü**
  - `gemini`: On the first hill is the Sultan Ahmed Mosque, with its six minarets, it's very grand,
- [2:25] **eserlerinden bir tanesi olan Ayasofya. Yani kutsal**
  - `gemini`: and right across is what I consider to be one of the most extraordinary works in the history of world architecture, Hagia Sophia.
- [2:29] **bilgelik kilisesi bulunuyor ki şu anda bir müze olarak kullanılıyor ve içine girdiğinizde iki dinin bir arada kardeşlik içinde görebileceğiniz**
  - `gemini`: That is, the Church of Holy Wisdom, which is currently used as a museum, and when you enter, you see two religions living together in brotherhood.
- [2:37] **dünyadaki tek mekan olarak geçiyor.**
  - `gemini`: It's one of the only places in the world like that.
- [2:40] **Oradan ikinci tepeye geçiyoruz.**
  - `gemini`: From there, we go to the second hill.
- [2:42] **Bizi selamlayan karşımıza çıkan Nuri Osmaniye Camii tam kapalı çarşının girişinde.**
  - `gemini`: We are greeted by the Nuri Osmaniye Mosque, which is right at the entrance of the Grand Bazaar.
- [2:47] **3. Osman yaptırdığı için ne demiş? Osman'ın ışığı**
  - `gemini`: It was built by Osman III, so what did he call it?
- [2:49] **demiş ve gerçekten ışıklar içerisinde bir cami. Ama**
  - `gemini`: The light of Osman, and it really is a mosque full of light.
- [2:53] **3. tepeye gittiğinizde bana göre şehrin en muhteşem camii bulunuyor. Koca Sinan'ın**
  - `gemini`: But when you go to the third hill, in my opinion, it's one of the most magnificent mosques in the city.
- [2:57] **yaptığı Süleymaniye.**
  - `gemini`: It's the one built by Koca Sinan, the Süleymaniye.
- [3:00] **Kanuni'nin tahta çıkışının 30. yıl dönümünde yapmış bunu. Ve**
  - `gemini`: It's the one built for the 30th anniversary of Suleiman's accession to the throne.
- [3:04] **dört tane minareyle süslemiş bu**
  - `gemini`: And it has four minarets.
- [3:06] **camiyi. Neden dört tane minare?**
  - `gemini`: Why four minarets?
- [3:08] **Çünkü Kanuni Osmanlı'nın İstanbul'u fethinden sonra başa geçen**
  - `gemini`: Because Suleiman was the fourth Padishah of the Ottoman Empire after the conquest of Istanbul.
- [3:13] **4. Sultan. Ve aynı**
  - `gemini`: He was the fourth Sultan.
- [3:14] **zamanda 10 tane birbirinden güzel şerefe yani balkon yapmış. Bu da**
  - `gemini`: And at the same time, he was the 10th Sultan to have a beautiful balcony, or"şerefe," built.
- [3:20] **Kanuni'nin Osmanlı'nın kuruluşunda itibaren 10. Sultan olduğunu**
  - `gemini`: This also represents the 10th Sultan since the founding of the Ottoman Empire.
- [3:24] **gösteriyor. İsterseniz 4. tepeye doğru yola çıkalım ve karşımıza Fatih Camii'nin çıktığını göreceğiz.**
  - `gemini`: If you want, we can move on to the fourth hill and we will be greeted by the Fatih Mosque, which we will see.
- [3:30] **Fatih Camii aslında baktığınızda Osmanlı'nın 400 yıl yaşadığı saraydan çok uzaktı. Peki neden orayı**
  - `gemini`: The Fatih Mosque is actually, when you look at it, the palace where the Ottomans lived for 400 years was very far away.
- [3:36] **seçmiş? Aslında bir sebebi var.**
  - `gemini`: So why did he choose that place?
- [3:38] **Çünkü**
  - `gemini`: There's actually a reason.
- [3:39] **3. tepeye yapmış fakat 4. tepeye Fatih yapmış. Çünkü**
  - `gemini`: Because the third built it on the third hill, but the fourth hill, Fatih built it.
- [3:44] **orada Konstantin'in mezarı**
  - `gemini`: Because there was Constantine's tomb there.
- [3:47] **bulunuyor. Yani şehrimizi kuran kişinin mezarı ve havari kilisesinin 12 havariler kilisesinin içindeymiş.**
  - `gemini`: That is, the city was the tomb of the person who founded it, and the Church of the Apostles was the 12 apostles' church.
- [3:54] **Dolayısıyla kendisini çok önemli bir Roma İmparatorluğu özdeşleş diyor.**
  - `gemini`: Therefore, he was very important, a Roman Empire identified with it.
- [4:00] **4. tepeyi tercih etmiş Fatih.**
  - `gemini`: He preferred the fourth hill, Fatih.
- [4:02] **Ve çok enteresan bir şey daha söyleyeyim.**
  - `gemini`: And it's very interesting to say one more thing.
- [4:05] **Türbesi de hemen Konstantin'in türbesinin olduğu yere yapılmış.**
  - `gemini`: His tomb is also right next to Constantine's tomb.
- [4:08] **5. tepeye geldiğimizde ise muhteşem bir başka camiyle**
  - `gemini`: When we come to the fifth hill, we see another magnificent mosque.
- [4:12] **karşılaşıyoruz. Çarşamba'da Yavuz Sultan Selim Camii.**
  - `gemini`: We encounter the Çarşamba Yavuz Sultan Selim Mosque.
- [4:15] **Fatih'in devamında bulunuyor. Yavuz Sultan**
  - `gemini`: Fatih's continuation is located there.
- [4:18] **Selim Camii ve Kanuni'nin babası için yapılmış. Haliç'e**
  - `gemini`: The Yavuz Sultan Selim Mosque and Suleiman's father was built for him.
- [4:22] **muhteşem manzaraya bakan olağanüstü bir cami.**
  - `gemini`: It has a magnificent view of the Golden Horn.
- [4:24] **İsterseniz 6. tepeye gidelim.**
  - `gemini`: If you want, we can move on to the sixth hill.
- [4:27] **6. tepede ise Mihrimah Sultan Camii'ni**
  - `gemini`: On the sixth hill, there is the Mihrimah Sultan Mosque.
- [4:30] **göreceksiniz. Şimdi hep hikayeye vardır.**
  - `gemini`: Now, we've always had a story.

### Ayse Bilge Gunduz, WomenTech: English by a Turkey-based developer

Gemini Live Translate (its own sentences; source = its input transcript):

- [1:03] **or medium.**
  - `gemini`: veya orta.
- [1:03] **So why Python at the beginning? Because**
  - `gemini`: Yani neden Python en başta?
- [1:06] **it's relatively easy to learn and fast to write code. It's**
  - `gemini`: Çünkü nispeten öğrenmesi kolay ve hızlı kod yazılıyor.
- [1:11] **like writing in English it seems to me at least and very intuitive.**
  - `gemini`: Sanki İngilizce yazmak gibi bana öyle geliyor en azından ve çok sezgisel.
- [1:16] **And when we compare it with MATLAB and it's versatile and of course when we compare it with C, it's less performance.**
  - `gemini`: Ve bunu MATLAB ile karşılaştırdığımızda ve çok yönlü ve tabii ki karşılaştırdığımızda C ile, daha az performanslı.
- [1:28] **So uh why Python 3 because today I will explain everything in Python 3 because Python 2 is not supported anymore.**
  - `gemini`: Yani şey neden Python 3 çünkü bugün her şeyi açıklayacağım Python'da çünkü Python 2 artık desteklenmiyor yani.
- [1:40] **So if you're using if you're still using Python 2, I highly recommend to convert to Python 3 because it's easy.**
  - `gemini`: Yani eğer hala kullanıyorsanız Python 2'yi şiddetle tavsiye ederim Python 3'e geçmenizi çünkü kolay.
- [1:49] **So, I'd like to start first with NumPy and um NumPy is a fundamental package for scientific computing in Python.**
  - `gemini`: Yani, şunu söylemek istiyorum, önce NumPy ile başlayayım ve ve şey NumPy bir temel paket bilimsel hesaplama için Python'da.
- [2:01] **Uh we can easily uh import NumPy with an alias as we can see it in here.**
  - `gemini`: Eee, kolayca şey NumPy'ı içe aktarabiliriz ve bir takma adla görebileceğimiz gibi burada.
- [2:09] **And the first line and it's an N-dimensional array object in essentially in the core. So we can easily assign a number in any type. It can be**
  - `gemini`: Ve ilk satır ve bu bir N boyutlu dizi nesnesi aslında özünde Yani kolayca bir sayı atayabiliriz herhangi bir türde.
- [2:22] **integer, it can be float.**
  - `gemini`: Bu tam sayı olabilir, kayan nokta olabilir.
- [2:25] **And there is many functions in NumPy like math library in Python like there's an exponential function, absolute function as we can see it in here. We can easily**
  - `gemini`: Ve birçok fonksiyon var NumPy'da mesela matematik kütüphanesi Python'da mesela bir üstel fonksiyon, mutlak fonksiyon gibi burada görebileceğimiz gibi.
- [2:38] **read and with np.**
  - `gemini`: Kolayca okuyabilir ve np.
- [2:41] **e number and pi number and here are the outputs for our inputs.**
  - `gemini`: ile e sayısı ve pi sayısı ve işte çıktılar girdilerimiz için.
- [2:48] **So and okay.**
  - `gemini`: Yani ve tamam.
- [2:52] **We told that it's an N-dimensional array object for NumPy, right? So it's so**
  - `gemini`: Dedik ki bu bir N boyutlu dizi nesnesi NumPy için, değil mi?
- [2:57] **easy to use with especially with array manipulation um things when we would like to do. Like we**
  - `gemini`: Yani kullanımı çok kolay, özellikle dizilerle ve dizi manipülasyonu ile şey şeyler yaparken yapmak istediğimizde gibi.
- [3:06] **can define an array easily. We can define a data type. It is referred to data type and we can use print function to print the array itself easily like in the output we can I hope you can see it in here.**
  - `gemini`: Mesela bir dizi tanımlayabiliriz kolayca ve bir veri türü tanımlayabiliriz bu veri türü olarak adlandırılır ve kullanabiliriz yazdırma fonksiyonunu yazdırmak için diziyi kolayca tıpkı çıktıda görebileceğimiz gibi umarım görebilirsiniz burada.
- [3:23] **And we can ask to see the dimension dimensional of the um array itself. It is one as**
  - `gemini`: Ve şunu sorabiliriz boyutunu görmek için boyutlu olduğunu şey dizinin kendisinin.
- [3:31] **we can see it in here.**
  - `gemini`: Bu bir, burada görebileceğimiz gibi.
- [3:34] **And we can easily get the shape which is four you can see above like there's a four item in our array and we can ask data type as well.**
  - `gemini`: Ve kolayca şeklini alabiliriz ki bu da dört demek görebilirsiniz yukarıda olduğu gibi dört öğeli bir dizimiz var ve sorabiliriz veri türünü de.
- [3:48] **which is a float.**
  - `gemini`: ki bu da bir kayan nokta.
- [3:50] **So as I told you before it's an array object. If it's**
  - `gemini`: Yani dediğim gibi daha önce bu bir dizi nesnesi.
- [3:54] **one dimensional, we can easily call it as vector. So if we**
  - `gemini`: Eğer tek boyutluysa kolayca buna vektör diyebiliriz.
- [3:58] **would like to do some actions over our array, one dimensional array or vector, whatever you call, it is so easy.**
  - `gemini`: Yani eğer istersek bazı işlemler yapmak istersek dizimiz üzerinde tek boyutlu bir dizi veya vektör, neyse artık, bu çok kolay.
- [4:09] **So I create a figure in here to show directly by writing A, we say, I mean, this is then we call it A, like we did in here.**
  - `gemini`: Yani ben oluşturuyorum ve burada bir şekil gösteriyorum doğrudan A yazarak diyoruz ki yani, bu o zaman buna A diyoruz tıpkı daha önce yaptığımız gibi burada.
- [4:29] **So I'm calling as A. Or we can write A and brackets and colon in the middle. It means**
  - `gemini`: Yani ben buna A diyorum ve ya da yazabiliriz A ve parantezleri ve iki noktayı ortaya koyabiliriz.
- [4:38] **that whole items in the array. And**
  - `gemini`: Bu, tüm öğeler dizideki anlamına gelir.
- [4:41] **we can if we if we would like to specific indices in the array, we can easily write the index number like we did in different**
  - `gemini`: Ve biz eğer istersek belirtmek istersek belirli indeksleri dizide, kolayca indeksi yazabiliriz tıpkı daha önce yaptığımız gibi farklı dillerde.
- [4:52] **languages, programming languages. So this is**
  - `gemini`: programlama dillerinde.
- [4:53] **the zero this is one, this is two, three and four. If we write**
  - `gemini`: Yani bu sıfır bu bir bu iki üç ve dört.
- [4:58] **one, then we can reach the two.**
  - `gemini`: Eğer bir yazarsak, o zaman ulaşabiliriz ikiye.
- [5:03] **So we can ask for for example like in here between one and**
  - `gemini`: Yani biz isteyebiliriz örneğin burada olduğu gibi bir ile arasında

### Gonul Ayci, PyCon DE lightning talk: English by a Turkey-based developer

Gemini Live Translate (its own sentences; source = its input transcript):

- [0:07] **Hayır. I'm Gönül**
  - `gemini`: Hayır.
- [0:07] **and this is Turkey.**
  - `gemini`: Ben Gönül ve burası Türkiye.
- [0:09] **Uh, we will organize our first Pycon Turkey conference. And it's yeah.**
  - `gemini`: Şey, biz ilk Pycon'umuzu düzenleyeceğiz ve bu evet.
- [0:17] **Yeah.**
  - `gemini`: Evet.
- [0:23] **Uh, it will be held in Istanbul on second and third of May next year.**
  - `gemini`: Şey, İstanbul'da düzenlenecek 2 ve 3 Mayıs'ta gelecek yıl.
- [0:29] **And we have a plan to open our call for papers on late November of this year.**
  - `gemini`: Ve bir planımız var çağrımızı açmak için makaleler Kasım sonu gibi bu yıl.
- [0:35] **And if you are interested, this is our website and you can subscribe our newsletter.**
  - `gemini`: Ve eğer ilgileniyorsanız, bu bizim web sitemiz ve haber bültenimize abone olabilirsiniz.
- [0:42] **And talks will be in English, but maybe uh as well as in Turkish.**
  - `gemini`: Ve konuşmalar İngilizce olacak, ama belki eee Türkiye'de olduğu gibi Türkçe de.
- [0:50] **And I want to mention a little bit about our Python**
  - `gemini`: Ve ben biraz bahsetmek istiyorum bizim Python topluluğumuzdan.
- [0:55] **community in Istanbul.**
  - `gemini`: İstanbul'daki.
- [0:56] **We have a huge community uh we have more than 9 thousand people on our meetup page and we will organize our night night meetups on next next week.**
  - `gemini`: Çok büyük bir topluluğumuz var, eee binden fazla 9 bin kişi meetup sayfamızda ve biz düzenleyeceğiz gece gece buluşmalarımızı önümüzdeki hafta.
- [1:13] **And we have a Django Girls community since 2015 and we have a hackathon.**
  - `gemini`: Ve bir Django Girls topluluğumuz var 2015'ten beri ve bir hackathon'umuz var.
- [1:20] **Last year and these are pictures from our meetups.**
  - `gemini`: Geçen yıl ve bunlar eee resimler bizim haftalık buluşmalarımızdan.
- [1:26] **And And these are from Django Girls events and hackathons.**
  - `gemini`: Ve Ve bunlar da Django Girls'ten etkinlikler ve hackathonlar.
- [1:33] **And that's all.**
  - `gemini`: Ve bu kadar.
- [1:35] **If you are interested, interested, uh welcome to Turkey next year on May second and third.**
  - `gemini`: Eğer ilgileniyorsanız, ilgileniyorsanız, eee Pycon'a Türkiye'ye hoş geldiniz gelecek yıl 2 ve 3 Mayıs'ta.

### Python Saati #85 (pyistanbul), from 18:00: Turkish tech talk

Gemini Live Translate (its own sentences; source = its input transcript):

- [18:03] **Ben kurşun silindirle sarıyorum. Eee**
  - `gemini`: I'm wrapping it with a lead cylinder.
- [18:04] **buna yukarıdan bir yoğun ışık gönderince bunu belirli bir sıcaklık ve basınçla çıkarabilince zincirleme reaksiyon doğuyor.**
  - `gemini`: Uh, I'm putting a strong light on it from above, and by applying a certain temperature and pressure, I can trigger a chain reaction.
- [18:12] **Ve 450 gramlık uranyum çekirdeği artık kendisi o zincirleme reaksiyonu sürdürebilir hale geliyor. Ben istediğim**
  - `gemini`: And a 450-gram uranium core itself becomes capable of sustaining that chain reaction.
- [18:18] **süre boyunca ama yine yaptığım şey bundan ürettiğim sıcaklıkla çark çevirmek.**
  - `gemini`: As long as I want, but what I'm doing is using the heat generated to turn a wheel.
- [18:23] **E dolayısıyla enerji kaynaklarımız değişse de kullandığımız alet edevat o**
  - `gemini`: So, our energy sources may change, but the tools we use are the same.
- [18:28] **kadar değişmiyor. İnsan olarak**
  - `gemini`: People don't change that much.
- [18:30] **Şimdi geriye doğru gidersek biraz önce makine aracı eee tanımlamıştık.**
  - `gemini`: Now, if we go back in time, as I mentioned earlier, a machine is a tool that we defined.
- [18:38] **Makine hani birden fazla parçadan oluşuyor ve bir mekanik güç kullanıyordu. Aslında**
  - `gemini`: A machine, you know, is made of more than one part and uses mechanical power.
- [18:43] **alet dediğimiz şey ona çok benziyor.**
  - `gemini`: Actually, a tool is very similar to that.
- [18:46] **E pense de de kullandığın başka bir mekanik güç kaynağı. Elim**
  - `gemini`: And pliers are another mechanism you use that uses mechanical power.
- [18:50] **tornavida da kullandığım başka bir güç kaynağı. Elim.**
  - `gemini`: My hand is another power source I use.
- [18:50] **tornavida da kullandığım başka bir güç kaynağı. Elim.**
  - `gemini`: My hand.
- [18:53] **Araç da elde tutulan yani alet edevat dediğimiz şey de tool da elde tutulan olmasının nedeni aslında mekanik gücü ben elimle sağlıyorum. Dolayısıyla**
  - `gemini`: A tool is also a handheld device, so what we call a tool is also a handheld device, and the reason is that I can provide the mechanical power with my hand.
- [19:01] **aslında baktığımızda makinayla araç kavramı birbirine çok**
  - `gemini`: So, actually, when you look at it, a machine and a tool are very similar.
- [19:06] **yakın bir yerde duruyor.**
  - `gemini`: They are very close.
- [19:07] **Yani bir tanesinin birden fazla parçası var tanım itibariyle. Birbirine çok yakın yerlerde duruyorlar.**
  - `gemini`: So, one has more than one part, by definition, They are very close to each other.
- [19:13] **Şimdi bu iki tanımı birbirinin üzerine koyarsak herhangi bir bilgisayar, herhangi bir makine, bir server, laptop, tablet, akıllı telefon, web kamerası, ne bileyim içinde herhangi**
  - `gemini`: Now, this two definitions if we put them on top of each other, any computer, any machine, a server, a laptop, a tablet, a smartphone, a webcam, I don't know,
- [19:25] **elektronik bir şeyle çalışan bir cihaz aslında totalde bir araçtan**
  - `gemini`: anything with electronics that works with a device is actually a total of a tool.
- [19:31] **ibaret. Güç kaynağı başka bir şey.**
  - `gemini`: The power source is something else.
- [19:33] **E parça birden fazla parçadan oluşabilir. Amenna.**
  - `gemini`: Uh, the part is made of more than one part.
- [19:33] **E parça birden fazla parçadan oluşabilir. Amenna.**
  - `gemini`: Okay.
- [19:37] **E altında yatan başka teknolojilerin üzerine konularak yapılmış. Dolayısıyla**
  - `gemini`: Uh, the underlying technologies are built on top of each other.
- [19:41] **bunların hepsi birer araç.**
  - `gemini`: So, all of these are tools.
- [19:44] **Makine dediğimiz şey aslında çok özünde**
  - `gemini`: It's not a machine, actually, at its core.
- [19:47] **belli bir amaca yönelik bir güç kaynağı olan bir**
  - `gemini`: It's a tool for a specific purpose that has a power source.
- [19:50] **araçtan ibaret. Bir**
  - `gemini`: It's a tool.
- [19:51] **tool'dan ibaret.**
  - `gemini`: It's a tool.
- [19:52] **E biz makinalarla yarış yapmak zorunda değiliz.**
  - `gemini`: Uh, we with machines are competing with them.
- [19:57] **Ya**
  - `gemini`: We don't have to.
- [19:58] **çünkü makinalar birer araç. Ya**
  - `gemini`: Because machines are tools.
- [20:00] **tornavidayla yarışmıyorum. Pense**
  - `gemini`: Like, I'm not competing with a screwdriver.
- [20:02] **ile yarışmıyorum. Bilgisayarımla da**
  - `gemini`: I'm not competing with pliers.
- [20:04] **yarışmıyorum. O işletim sistemiyle de yarışmıyorum.**
  - `gemini`: I'm not competing with my computer either.
- [20:06] **İçinde kullandığım benim ürettiğim**
  - `gemini`: I'm not competing with the operating system either.
- [20:08] **algoritmayla da yarışmıyorum. Daha doğrusu yarışmak**
  - `gemini`: I'm not competing with the algorithm I use either.
- [20:10] **zorunda değilim. Yani beni yenebilir**
  - `gemini`: Or rather, I don't have to compete.
- [20:12] **mi? Lisanen doğru bir soru değil.**
  - `gemini`: So, can it beat me?
- [20:13] **Yani tornavida**
  - `gemini`: That's not a correct question.
- [20:15] **zaten beni yenmeye çalışmıyor. E falanca**
  - `gemini`: I mean, the screwdriver isn't trying to beat me.
- [20:17] **eee segmentasyon algoritması beni yenmeye çalışmıyor.**
  - `gemini`: And so-and-so segmentation algorithm isn't trying to beat me.

### Python Saati #102 (pyistanbul), Celery: regular Turkish tech presentation

Gemini Live Translate (its own sentences; source = its input transcript):

- [0:05] **Şimdi öncelikle bir ekranımı paylaşayım. Bakalım onu**
  - `gemini`: Now, first of all, let me share my screen.
- [0:07] **becerebilecek miyiz?**
  - `gemini`: Let's see if we can do that.
- [0:12] **Evet.**
  - `gemini`: Yes.
- [0:14] **Tamam.**
  - `gemini`: Okay.
- [0:15] **Şimdi sanıyorum ekran geliyor ama chat'i görememem tabii ki büyük bir talihsizlik oldu.**
  - `gemini`: Now, I think the screen is coming up, but I can't see the chat, which is of course a big misfortune.
- [0:23] **Bir saniye.**
  - `gemini`: One second.
- [0:24] **Muhteşem ararız.**
  - `gemini`: It's a great search.
- [0:27] **Chat'leri göremememi sağlıyor. O**
  - `gemini`: Not being able to see the chat is what's happening.
- [0:30] **bunu da buraya alalım. Evet şimdi**
  - `gemini`: Let's move this here too.
- [0:31] **görüyorum.**
  - `gemini`: Yes, now I can see it.
- [0:33] **Evet.**
  - `gemini`: Yes.
- [0:34] **Eee şimdi bu sunumu ben daha önce yaptım. Eee eee EuroPython'da yaptığım bir eee sunum.**
  - `gemini`: Uh, now this presentation I've done before Uh, uh at EuroPython I did a uh presentation.
- [0:46] **Eee 2017 yılında EuroPython'da yaptım. Rimini'de. Tabii**
  - `gemini`: Uh, in 2017 I did it at EuroPython in Rimini.
- [0:50] **İngilizceydi o sunum. Eee burada**
  - `gemini`: Of course, that presentation was in English.
- [0:52] **yine aynı slaytları kullanacağım. Çünkü dünyasında hiçbir şey değişmedi.**
  - `gemini`: Uh, I'll use the same slides here because nothing has changed in the world.
- [0:56] **Muhtemelen 5 sene önce Fatih Erik'in yaptığı sunumla arasında da çok bir şey değişmedi.**
  - `gemini`: Probably 5 years ago, there's not much difference between this and Fatih Erik's presentation.
- [1:01] **6 yıl olarak da birçok şeyler değişti.**
  - `gemini`: In 6 years, a lot of things have changed.
- [1:03] **Ama kullanım ve bu sunumun kapsamındaki şeyler açısından**
  - `gemini`: But the usage and the scope of this presentation haven't changed much.
- [1:07] **çok bir değişiklik yok.**
  - `gemini`: There's not much of a change.
- [1:09] **Eee kendimden bahsedeyim.**
  - `gemini`: Uh, let me introduce myself.
- [1:11] **Eee ben Yiğit Güler.**
  - `gemini`: Uh, I'm Yiğit Güler.
- [1:14] **İstanbul üyelerinden biriyim.**
  - `gemini`: One of the Istanbul members.
- [1:16] **Yaklaşık eee 7-8 yıldır buluşmaları düzenli olarak**
  - `gemini`: About uh 7-8 years ago I've been organizing the meetings regularly.
- [1:23] **düzenliyoruz. Eee Hipo'da backend developer olarak**
  - `gemini`: Uh, I'm a backend developer at Hipo.
- [1:28] **çalışıyorum. Eee sunumun başında bana göre çok önemli olan bir şeyden başlayacağım.**
  - `gemini`: Uh, the beginning of the presentation, in my opinion, I'm going to start with something very important.
- [1:34] **Dünyada Python sürekli ilerliyor ve günden güne daha popüler bir**
  - `gemini`: In the world, Python is constantly advancing and becoming more popular by the day.
- [1:41] **dil haline geliyor. Bence bunun en önemli sebeplerinden bir tanesi de bu popülerleşmeyle beraber gelen değişik disiplinlerden kullanıcıların aynı dili**
  - `gemini`: I think the most important reason for this is that this popularization also brings different disciplines from users who use the same language.
- [1:52] **kullanıyor olması. Örnek vermek gerekirse eee makine öğrenmesiyle uğraşan insanlar da Python kullanıyorlar.**
  - `gemini`: For example, uh, with machine learning and people who use Python also use it.
- [1:59] **Web sitesi yapan bizim gibi veya API geliştiren insanlar da Python**
  - `gemini`: People who make websites like us or develop APIs also use Python.
- [2:05] **kullanıyorlar. Eee astro ile uğraşan bilim insanları da Python**
  - `gemini`: Uh, astronomy and people who work in science also use Python.
- [2:11] **kullanabiliyorlar. Ve bu çok büyük bir güç.**
  - `gemini`: And this is a very big strength.
- [2:13] **Eee öyle ki bence Python Node JS veya Ruby'ye göre en önemli Node JS bir diliyle ama bir backend framework'ü**
  - `gemini`: Uh, so much so that I think Python is better than Node JS or Ruby in the most important way, even though it's a Node JS language,
- [2:22] **olarak söyleyeyim.**
  - `gemini`: but as a backend framework.
- [2:24] **Eee bir web projesi yaparken Python'un en önemli avantajı eee çok değişik disiplinlerden değişik kodlara ulaşabilmek, değişik kütüphanelere ulaşabilmek ve bunları**
  - `gemini`: Uh, a web project using Python, the most important advantage is that there are many different disciplines and different codes that you can access,
- [2:34] **kullanabilmek.**
  - `gemini`: different libraries you can access and use.
- [2:37] **Ama tabii ki birçok kütüphane özellikle eee mesela genişleme genişleme işlerinde kullanılan kütüphaneler veya video processing'de kullanılan kütüphaneler. Bunlar**
  - `gemini`: But of course, there are many libraries, especially uh for example, extension extension libraries used in or video processing libraries are used.
- [2:50] **zaman alan işlemler**
  - `gemini`: These take time-consuming operations.
- [2:52] **olabiliyor. Ve biz HTTP kuralları gereği bir request response cycle içinde hareket**
  - `gemini`: And we have HTTP rules that require a request-response cycle.
- [2:59] **ediyoruz. Yani bir istek istemciden geliyor. Sunucunun belli bir süresi var.**
  - `gemini`: That is, a request comes from the client and the server has a certain amount of time.
- [3:06] **Belli bir süreden fazla olursa bu tip 502 hatalarını görebiliyoruz.**
  - `gemini`: If it takes longer than a certain amount of time, these types of 502 errors can occur.
