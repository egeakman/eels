# Translation outputs for review

**EN**: Today I want to talk about how we turned a slow Python function into a Rust module.  
_reference_: Bugün yavaş bir Python fonksiyonunu nasıl bir Rust modülüne dönüştürdüğümüzden bahsetmek istiyorum.  
`opus-mt`: Bugün yavaş bir Python fonksiyonunu nasıl Rust modülüne dönüştürdüğümüzden bahsetmek istiyorum.  
`tg4b`: Bugün, yavaş bir Python fonksiyonunu Rust modülüne dönüştürme sürecini konuşmak istiyorum.  
`hymt1.8b`: Bugün, yavaş çalışan bir Python fonksiyonunu nasıl Rust modülüne dönüştürdüğümüzden bahsetmek istiyorum.  

**EN**: The profiler showed that ninety percent of the time was spent in one loop.  
_reference_: Profilleyici, sürenin yüzde doksanının tek bir döngüde geçtiğini gösterdi.  
`opus-mt`: Profilleyici, zamanın yüzde doksanının tek bir döngüde geçtiğini gösterdi.  
`tg4b`: Analiz, %90’ının tek bir döngü içinde harcanmış olduğunu gösterdi.  
`hymt1.8b`: Analiz sonuçlarına göre, zamanın %90’ı tek bir döngü içinde geçiyor.  

**EN**: So the first question is, do you really need a message broker?  
_reference_: Yani ilk soru şu: gerçekten bir mesaj aracısına ihtiyacınız var mı?  
`opus-mt`: Yani ilk soru, gerçekten bir mesaj komisyoncusuna ihtiyacınız var mı?  
`tg4b`: İlk soru ise, gerçekten bir mesaj broker'ına ihtiyacınız var mı?  
`hymt1.8b`: Yani, ilk soru şu: Gerçekten bir mesaj aracına ihtiyacınız var mı?  

**EN**: Most task queues use Redis or RabbitMQ,  
_reference_: Çoğu görev kuyruğu Redis ya da RabbitMQ kullanır,  
`opus-mt`: Çoğu görev kuyruğu Redis veya RabbitMQ kullanır,  
`tg4b`: Çoğu görev kuyruğu, Redis veya RabbitMQ kullanır  
`hymt1.8b`: Çoğu görev kuyruğu, Redis veya RabbitMQ kullanır  

**EN**: but for small projects you can just use your database.  
_reference_: ama küçük projeler için doğrudan veritabanınızı kullanabilirsiniz.  
`opus-mt`: Ancak küçük projeler için sadece veritabanınızı kullanabilirsiniz.  
`tg4b`: Ancak küçük projeler için, sadece veritabanınızı kullanmanız yeterlidir.  
`hymt1.8b`: Küçük projeler için ise, sadece kendi veritabanınızı kullanabilirsiniz.  

**EN**: A regular expression is just a tiny language for describing patterns in text.  
_reference_: Düzenli ifade, metindeki kalıpları tanımlamak için kullanılan küçük bir dildir.  
`opus-mt`: Düzenli bir ifade, metindeki kalıpları tanımlamak için sadece küçük bir dildir.  
`tg4b`: Düzenli bir ifade, metindeki desenleri tanımlamak için kullanılan, oldukça küçük bir dildir.  
`hymt1.8b`: Düzenli ifade, metindeki desenleri tanımlamak için kullanılan küçük bir dildir.  

**EN**: The plus sign means one or more, and the star means zero or more.  
_reference_: Artı işareti bir veya daha fazla, yıldız ise sıfır veya daha fazla anlamına gelir.  
`opus-mt`: Artı işareti bir veya daha fazla, yıldız ise sıfır veya daha fazla anlamına gelir.  
`tg4b`: "+" işareti bir veya daha fazla anlamına gelir, "*" işareti ise sıfır veya daha fazla anlamına gelir.  
`hymt1.8b`: “Artı işareti”, bir veya daha fazla anlamına gelir; yıldız işareti ise sıfır veya daha fazla anlamına gelir.  

**EN**: In Django, query parameters are available on the request object.  
_reference_: Django'da sorgu parametrelerine request nesnesi üzerinden erişilebilir.  
`opus-mt`: Django'de, istek nesnesinde sorgu parametreleri mevcuttur.  
`tg4b`: Django'da, sorgu parametreleri istek nesnesinde mevcuttur.  
`hymt1.8b`: Django’da, sorgu parametreleri, request nesnesinde mevcuttur.  

**EN**: If you have ever written a REST API, you know this pain.  
_reference_: Daha önce bir REST API yazdıysanız bu acıyı bilirsiniz.  
`opus-mt`: Daha önce bir REST API'si yazdıysanız, bu acıyı bilirsiniz.  
`tg4b`: Eğer hiç REST API geliştirmişseniz, bu zorluğu bilirsiniz.  
`hymt1.8b`: Eğer daha önce bir REST API yazmışsanız, bu zorluğu kesinlikle biliyorsunuzdur.  

**EN**: We run the model directly on the edge device, without any cloud.  
_reference_: Modeli hiçbir bulut kullanmadan doğrudan uç cihazda çalıştırıyoruz.  
`opus-mt`: Modeli doğrudan kenar cihazında, herhangi bir bulut olmadan çalıştırıyoruz.  
`tg4b`: Modeli doğrudan cihaz üzerinde, herhangi bir bulut olmadan çalıştırıyoruz.  
`hymt1.8b`: Modeli doğrudan edge cihazlar üzerinde çalıştırıyoruz; herhangi bir bulut hizmeti kullanmıyoruz.  

**EN**: It processes about thirty frames per second on a small GPU.  
_reference_: Küçük bir GPU üzerinde saniyede yaklaşık otuz kare işliyor.  
`opus-mt`: Küçük bir GPU'da saniyede yaklaşık otuz kareyi işler.  
`tg4b`: Küçük bir GPU üzerinde yaklaşık olarak saniyede 30 kare işlemektedir.  
`hymt1.8b`: Küçük bir GPU’da saniyede yaklaşık otuz kareyi işleyebiliyor.  

**EN**: Every token you send to the model costs money and adds latency.  
_reference_: Modele gönderdiğiniz her token para tutar ve gecikmeyi artırır.  
`opus-mt`: Modele gönderdiğiniz her jeton paraya mal olur ve gecikme ekler.  
`tg4b`: Gönderdığınız her token, model için para maliyeti oluşturur ve gecikmeye neden olur.  
`hymt1.8b`: Modela gönderdiğiniz her bir gönderi, para gerektirir ve aynı zamanda gecikmeyi de beraberinde getirir.  

**EN**: Let me show you a quick demo, if the Wi-Fi cooperates.  
_reference_: Wi-Fi izin verirse size hızlı bir demo göstereyim.  
`opus-mt`: Wi-Fi işbirliği yaparsa size hızlı bir demo göstereyim.  
`tg4b`: Lütfen, Wi-Fi bağlantısı sağlandığında, hızlı bir demo göstermek isterim.  
`hymt1.8b`: Eğer Wi-Fi sistemi uyumluysa, size hızlı bir örnek vereyim.  

**EN**: It talks like a human, but it is not a human.  
_reference_: İnsan gibi konuşuyor ama insan değil.  
`opus-mt`: İnsan gibi konuşuyor ama insan değil.  
`tg4b`: İnsan gibi konuşmasına rağmen, aslında bir insan değildir.  
`hymt1.8b`: Kulağa insan gibi geliyor, ancak aslında insan değildir.  

**EN**: DuckDB can read Parquet files directly, so you don't need a cluster.  
_reference_: DuckDB, Parquet dosyalarını doğrudan okuyabilir, bu yüzden bir kümeye ihtiyacınız yok.  
`opus-mt`: DuckDB, Parquet dosyalarını doğrudan okuyabilir, böylece bir kümeye ihtiyacınız olmaz.  
`tg4b`: DuckDB, Parquet dosyalarını doğrudan okuyabilir, bu nedenle bir kümeye ihtiyacınız olmaz.  
`hymt1.8b`: DuckDB, Parquet dosyalarını doğrudan okuyabiliyor; bu yüzden bir kümeye ihtiyacınız yoktur.  

**EN**: and that was basically the whole trick.  
_reference_: ve temelde bütün numara buydu.  
`opus-mt`: Ve esas olarak tüm hile buydu.  
`tg4b`: Ve bu, aslında tüm stratejiydi.  
`hymt1.8b`: Ve bu, aslında tüm hikayeydi.  

**EN**: So, um, where was I? Right, the benchmarks.  
_reference_: Şey, nerede kalmıştım? Evet, performans testleri.  
`opus-mt`: Peki, ben neredeydim? Doğru, ölçütler.  
`tg4b`: Tamam, yani, neredeydim? Evet, kilometre taşları.  
`hymt1.8b`: Peki, nerede kalmıştım? Evet, ölçütler…  

**EN**: Thank you so much, and I'm happy to take questions.  
_reference_: Çok teşekkür ederim, sorularınızı yanıtlamaktan memnuniyet duyarım.  
`opus-mt`: Çok teşekkür ederim ve soru sormaktan mutluluk duyarım.  
`tg4b`: Çok teşekkür ederim, ve sorularınızı almak için mutluyum.  
`hymt1.8b`: Çok teşekkür ederim. Sorularınızı yanıtlamaktan memnuniyet duyarım.  

**EN**: The garbage collector does not know about objects that live in Rust.  
_reference_: Çöp toplayıcı, Rust'ta yaşayan nesnelerden haberdar değildir.  
`opus-mt`: Çöp toplayıcısı Rust'de yaşayan nesneler hakkında bilgi sahibi değildir.  
`tg4b`: Garbage toplayıcı, Rust'ta yaşayan nesneler hakkında bilgi sahibi değildir.  
`hymt1.8b`: Çöp toplama sistemi, Rust’ta bulunan nesneler hakkında hiçbir bilgiye sahip değildir.  

**EN**: Write small patterns, test them often, and add comments.  
_reference_: Küçük kalıplar yazın, sık sık test edin ve yorum ekleyin.  
`opus-mt`: Küçük desenler yazın, sık sık test edin ve yorumlar ekleyin.  
`tg4b`: Küçük desenler yazın, sık sık test edin ve açıklamalar ekleyin.  
`hymt1.8b`: Küçük desenler oluşturun, bunları sık sık test edin ve gerekli yorumları ekleyin.  

**EN**: You can install it with pip, or with uv if you like speed.  
_reference_: pip ile ya da hız seviyorsanız uv ile kurabilirsiniz.  
`opus-mt`: Pip ile veya hızı seviyorsanız uv ile yükleyebilirsiniz.  
`tg4b`: Bu paketi pip ile veya daha hızlı olmak isterseniz uv ile de kurabilirsiniz.  
`hymt1.8b`: Bunu pip aracılığıyla da, ya da hızlı bir şekilde kullanmak istiyorsanız uv aracılığıyla da kuracaksınız.  

**EN**: When the queue is empty, the worker just sleeps for a second.  
_reference_: Kuyruk boş olduğunda işçi bir saniye uyur.  
`opus-mt`: Kuyruk boşaldığında, işçi bir saniyeliğine uyur.  
`tg4b`: Kuyruk boş olduğunda, çalışan sadece bir saniye uyur.  
`hymt1.8b`: Kuyruk boş olduğunda, işçi sadece bir saniye kadar uyur.  

**EN**: This is where things get interesting.  
_reference_: İşte burada işler ilginçleşiyor.  
`opus-mt`: İşler burada ilginçleşiyor.  
`tg4b`: Burada ilginç şeyler başlıyor.  
`hymt1.8b`: İşte bu noktada durum ilginç hale geliyor.  

**EN**: who has used FastAPI before? Raise your hand.  
_reference_: daha önce FastAPI kullanan var mı? Elinizi kaldırın.  
`opus-mt`: FastAPI'i daha önce kim kullandı? Elinizi kaldırın.  
`tg4b`: Hangi kişi FastAPI'yi daha önce kullanmış? Elinizi kaldırın.  
`hymt1.8b`: Daha önce FastAPI kullanan kimler var? Elinizi kaldırın.  

**TR**: Herkese merhaba, bugün size FastAPI ile sıfırdan üretime nasıl geçtiğimizi anlatacağım.  
_reference_: Hello everyone, today I will tell you how we went from zero to production with FastAPI.  
`opus-mt`: Hello everyone, today I'll tell you how we went from zero to production with FastAPI.  
`tg4b`: Hello everyone, today I’ll be explaining how we transitioned to using FastAPI from scratch.  
`hymt1.8b`: Hello everyone. Today, I’ll explain how I went from zero to creating production-level applications using FastAPI.  

**TR**: Önce küçük bir prototip yazdık, sonra veritabanı bağlantısını ekledik.  
_reference_: First we wrote a small prototype, then we added the database connection.  
`opus-mt`: First we wrote a small prototype, then we added the database link.  
`tg4b`: First, we created a small prototype, and then we added the database connection.  
`hymt1.8b`: First, we wrote a small prototype. Then, we added the database connection functionality to it.  

**TR**: Asıl zorluk testleri ve dağıtımı otomatik hale getirmekti.  
_reference_: The real challenge was automating the tests and the deployment.  
`opus-mt`: The main challenge was to automate testing and distribution.  
`tg4b`: The main challenge was to automate the creation and distribution of tests.  
`hymt1.8b`: The real challenge was to make the testing and distribution processes automated.  

**TR**: Docker kullanarak her ortamı aynı hale getirdik.  
_reference_: Using Docker, we made every environment the same.  
`opus-mt`: Using Docker, we have made each environment the same.  
`tg4b`: We’ve standardized every environment using Docker.  
`hymt1.8b`: By using Docker, we have made every environment identical to each other.  

**TR**: Üretimde neyin bozulduğunu hemen görmek istiyorduk.  
_reference_: We wanted to see immediately what was breaking in production.  
`opus-mt`: We wanted to see immediately what was broken in production.  
`tg4b`: We really wanted to see what had gone wrong in the production process immediately.  
`hymt1.8b`: We wanted to see right away what had gone wrong in the production process.  

**TR**: MicroPython ile küçük bir mikrodenetleyici üzerinde Python çalıştırabiliyorsunuz.  
_reference_: With MicroPython you can run Python on a small microcontroller.  
`opus-mt`: With MicroPython, you can run Python on a small microcontroller.  
`tg4b`: You can run Python on a small microcontroller using MicroPython.  
`hymt1.8b`: With MicroPython, you can run Python programs on a small microcontroller.  

**TR**: E-ink ekranın en güzel yanı, güç kesildiğinde bile görüntünün kalması.  
_reference_: The best thing about an e-ink screen is that the image stays even when the power is cut.  
`opus-mt`: The best thing about the e-ink screen is that the image remains even when the power is cut.  
`tg4b`: The most beautiful thing about an e-ink screen is that it continues to display the image even when the power is turned off.  
`hymt1.8b`: The best thing about the E-ink screen is that the image remains visible even when the power is turned off.  

**TR**: Bu kartı yaklaşık iki yüz liraya aldım.  
_reference_: I bought this board for about two hundred lira.  
`opus-mt`: I got this card for about two hundred liras.  
`tg4b`: I bought this card for around two hundred lira.  
`hymt1.8b`: I bought this card for about two hundred lira.  

**TR**: PyCon Türkiye ilk kez yirmi on sekizde düzenlendi.  
_reference_: PyCon Turkey was first held in twenty eighteen.  
`opus-mt`: PyCon Turkey was held for the first time in twenty-eight.  
`tg4b`: PyCon Türkiye was held for the first time in 2018.  
`hymt1.8b`: PyCon Türkiye was held for the first time on the 28th of this month.  

**TR**: Gönüllüler olmasaydı bu etkinlik hiç gerçekleşmezdi.  
_reference_: Without the volunteers this event would never have happened.  
`opus-mt`: Without volunteers, this event would never have happened.  
`tg4b`: Without the volunteers, this event would not have happened at all.  
`hymt1.8b`: Without volunteers, this event wouldn’t have taken place at all.  

**TR**: Tembel değerlendirme sayesinde sadece ihtiyacımız olan veriyi hesaplıyoruz.  
_reference_: Thanks to lazy evaluation, we only compute the data we need.  
`opus-mt`: Through lazy assessment, we only calculate the data we need.  
`tg4b`: By using efficient evaluation, we are only calculating the data we actually need.  
`hymt1.8b`: With lazy evaluation, we only calculate the data that we actually need.  

**TR**: Yani kısacası, hem hızlı hem de tembel olabilirsiniz.  
_reference_: So in short, you can be both fast and lazy.  
`opus-mt`: So in short, you can be both quick and lazy.  
`tg4b`: Basically, you can be both fast and lazy.  
`hymt1.8b`: In short, you can be both fast and lazy at the same time.  

**TR**: Şimdi size kodun bu kısmını göstermek istiyorum,  
_reference_: Now I want to show you this part of the code,  
`opus-mt`: Now I want to show you this part of the code,  
`tg4b`: Now, I would like to show you this part of the code  
`hymt1.8b`: Now, I would like to show you this part of the code  

**TR**: çünkü asıl sihir burada oluyor.  
_reference_: because this is where the real magic happens.  
`opus-mt`: Because that's where the real magic happens.  
`tg4b`: Because the real magic happens here.  
`hymt1.8b`: Because it’s here that the real magic happens.  

**TR**: Bir sorunuz varsa konuşmadan sonra beni bulabilirsiniz.  
_reference_: If you have a question, you can find me after the talk.  
`opus-mt`: If you have any questions, you can find me after the conversation.  
`tg4b`: If you have any questions, please find me after the conversation.  
`hymt1.8b`: If you have any questions, you can find me after the conversation.  

**TR**: Bu fonksiyon bir liste alıyor ve bir sözlük döndürüyor.  
_reference_: This function takes a list and returns a dictionary.  
`opus-mt`: This function takes a list and returns a dictionary.  
`tg4b`: This function takes a list and returns a dictionary.  
`hymt1.8b`: This function takes a list as input, and returns a dictionary as output.  

**TR**: Hata ayıklarken en çok zamanı loglara bakarak geçirdik.  
_reference_: While debugging we spent most of the time looking at the logs.  
`opus-mt`: We spent the most time debugging by looking at logs.  
`tg4b`: When debugging, we would spend the most time looking at the logs.  
`hymt1.8b`: While removing errors, we spent most of our time looking at the logs.  

**TR**: Geçen yıl topluluk iki katına çıktı.  
_reference_: Last year the community doubled in size.  
`opus-mt`: Last year, the community doubled.  
`tg4b`: Last year, the group doubled in size.  
`hymt1.8b`: Last year, the community doubled in size.  

**TR**: Eee, nerede kalmıştım? Evet, performans kısmı.  
_reference_: Um, where was I? Right, the performance part.  
`opus-mt`: So, where was I?  
`tg4b`: “Hey, where was I? Yes, the performance section.”  
`hymt1.8b`: Eee, where did I stop? Yes, it’s the performance section.  

**TR**: Bu yaklaşımın bir dezavantajı var, o da bellek kullanımı.  
_reference_: This approach has one drawback, and that is memory usage.  
`opus-mt`: There is one downside to this approach, which is the use of memory.  
`tg4b`: One disadvantage of this approach is its memory usage.  
`hymt1.8b`: This approach has one disadvantage, and that is related to memory usage.  

**TR**: Uygulamayı Kubernetes yerine tek bir sunucuda çalıştırıyoruz.  
_reference_: We run the application on a single server instead of Kubernetes.  
`opus-mt`: We run the application on a single server instead of Kubernetes.  
`tg4b`: We are running the application on a single server instead of using Kubernetes.  
`hymt1.8b`: We run this application on a single server, instead of using Kubernetes.  

**TR**: Çok teşekkür ederim, hepinize iyi eğlenceler.  
_reference_: Thank you very much, and have fun, everyone.  
`opus-mt`: Thank you so much, have fun with all of you.  
`tg4b`: Thank you so much, have a wonderful time everyone.  
`hymt1.8b`: Thank you very much. Have a great time with everyone.  

**TR**: ve bu şekilde gecikmeyi yarıya indirdik.  
_reference_: and this way we cut the latency in half.  
`opus-mt`: And that's how we cut the delay in half.  
`tg4b`: and as a result, we reduced the delay by half.  
`hymt1.8b`: And in this way, we were able to reduce the delay by half.  

**TR**: Eğer sizin de böyle bir projeniz varsa, mutlaka paylaşın.  
_reference_: If you have a project like this too, be sure to share it.  
`opus-mt`: If you have such a project, you must share it.  
`tg4b`: If you have a project like that, please do share it.  
`hymt1.8b`: If you also have such a project, be sure to share it with us.  
