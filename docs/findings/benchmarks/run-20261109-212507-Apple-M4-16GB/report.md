# Real talks by Turkish speakers, scored against human captions

MacBook Air (Apple M4, 16 GB). WER = word error rate against the human captions (lower is better); live = the app's streaming recognition, offline = the same model on 28 s windows. A few words at the edges of each excerpt may not line up with the captions (about 1-2 points).

| Speech model | Talk | WER live | WER offline | ms per pass |
|---|---|---|---|---|
| turbo-750 | Elif Shafak, TED: English by a Turkish speaker (human EN + TR captions) | 6.5% | 7.2% | 809 |

| Translation model | Talk | chrF vs human Turkish translation | ms per sentence |
|---|---|---|---|
| opus-mt | Elif Shafak, TED: English by a Turkish speaker (human EN + TR captions) | 57.4 | 374 |

## Subtitles: what was heard live (best speech model) and each translation

### Elif Shafak, TED: English by a Turkish speaker (human EN + TR captions)

- **Stab it with as many rose thorns as the number of words she wanted to remove Then one by one she would encircle these thorns with dark ink.**
  - `opus-mt`: Çıkarmak istediği kelime sayısı kadar gül dikeni ile yapıştırın Sonra bu dikenleri tek tek koyu mürekkeple çevrelerdi.
- **A week later the patient would come back for a follow-up examination.**
  - `opus-mt`: Bir hafta sonra hasta tekrar muayene için gelecekti.
- **Now I'm aware that I should not be saying such things in front of an audience of scholars and scientists but the truth is of all the people who visited my grandmother for their skin conditions I did not see anyone go back unhappy or unhealed I asked her how she did this.**
  - `opus-mt`: Şimdi biliyorum ki, bu tür şeyleri bir bilim adamı ve bilim adamı seyircisi önünde söylememem gerekir, ama gerçek şu ki, büyükannemi ten koşulları için ziyaret eden tüm insanlar arasında, kimsenin mutsuz ya da iyileşmemiş bir şekilde geri döndüğünü görmedim.
- **was it the power of praying In response she said yes praying is effective but also beware of the power of circles From her I learned amongst many other things one very precious lesson that if you want to destroy something in this life be it an acne a blemish or the human soul all you need to do is to surround it with thick walls it will dry up inside now we all live in some kind of a social and cultural circle we all do we're born into a certain family nation, class but if we have no connection whatsoever with the worlds beyond the one we take for granted then we too run the risk of drying up inside Our imagination might shrink, our hearts might dwindle and our humanness might wither if we stay for too long inside our cultural cocoons.**
  - `opus-mt`: Dua etmenin gücü müydü? Cevap olarak evet dua etmenin etkili olduğunu söyledi ama aynı zamanda çevrelerin gücüne dikkat edin Diğer birçok şey arasında öğrendiğim çok değerli bir ders eğer bu hayatta bir şeyi yok etmek istiyorsanız bir akne lekesi veya insan ruhu olabilir Tek yapmanız gereken onu kalın duvarlarla sarmak, şimdi içinde kuruyacak hepimiz bir tür sosyal ve kültürel çevrede yaşıyoruz, ama biz ne olursa olsun belirli bir ulus içinde doğduk.
- **Our friends, neighbours, colleagues, family, if all the people in our inner circle resemble us, it means we are surrounded with our mirror image.**
  - `opus-mt`: Arkadaşlarımız, komşularımız, meslektaşlarımız, ailemiz, eğer yakın çevremizdeki tüm insanlar bize benziyorsa, bu bizim ayna imajımızla çevrili olduğumuz anlamına gelir.
- **Now one of the things women like my grandma do in Turkey is to cover mirrors with velvet or to hang them on the walls with their backs facing out.**
  - `opus-mt`: Şimdi Türkiye'de büyükannem gibi kadınların yaptığı şeylerden biri de aynaları kadife ile örtmek ya da arkaları dönük duvarlara asmak.
- **It's an old Eastern tradition based on the knowledge that it's not healthy for a human being to spend too much time staring at his own reflection Ironically, communities of the like-minded is one of the greatest dangers of today's globalized world and it's happening everywhere among liberals and conservatives, agnostics and believers, the rich and the poor, East and West alike.**
  - `opus-mt`: Bu, bir insanın kendi yansımasına ironik bir şekilde bakarak çok fazla zaman geçirmesinin sağlıklı olmadığı bilgisine dayanan eski bir Doğu geleneğidir, benzer düşünen topluluklar günümüzün küreselleşmiş dünyasının en büyük tehlikelerinden biridir ve liberaller ve muhafazakarlar, agnostikler ve inananlar, zenginler ve fakirler, Doğu ve Batı arasında her yerde gerçekleşmektedir.
- **We tend to form clusters based on similarity and then we produce stereotypes about other clusters of people.**
  - `opus-mt`: Benzerliğe dayalı kümeler oluşturma eğilimindeyiz ve daha sonra diğer insan kümeleri hakkında stereotipler üretiyoruz.
- **In my opinion, one way of transcending these cultural ghettos is through the art of storytelling.**
  - `opus-mt`: Bence bu kültürel gettoları aşmanın bir yolu hikâye anlatma sanatıdır.
- **Stories cannot demolish frontiers, but they can punch holes in our mental walls and through those holes we can get a glimpse of the other and sometimes even like what we see I started writing fiction at the age of eight.**
  - `opus-mt`: Hikayeler sınırları ortadan kaldıramaz, ancak zihinsel duvarlarımızda ve bu deliklerden delikler açabilirler, diğerini bir bakışta görebiliriz ve hatta bazen sekiz yaşında kurgu yazmaya başladığımı gördüğümüz gibi.
- **My mother came home one day with a turquoise notebook and asked me if I'd be interested in keeping a personal journal.**
  - `opus-mt`: Annem bir gün turkuaz bir defterle eve geldi ve kişisel bir günlük tutmak isteyip istemediğimi sordu.
- **In retrospect, I think she was slightly worried about my sanity.**
  - `opus-mt`: Geçmişe bakınca, sanırım aklımın başına gelmesinden biraz endişeliydi.
- **I was constantly telling stories at home, which was good, except I told this to imaginary friends around me, which was not so good.**
  - `opus-mt`: Evde sürekli hikayeler anlatıyordum, ki bu iyiydi, bunu etrafımdaki hayali arkadaşlara anlatmam dışında, ki bu pek de iyi değildi.
- **I was an introverted child to the point of communicating with coloured crayons and apologising to objects when I bumped into them.**
  - `opus-mt`: Renkli boya kalemleri ile iletişim kurma ve onlara çarptığımda nesnelerden özür dileme noktasına kadar içe dönük bir çocuktum.
- **So my mother thought it might do me good to write down my day-to-day experiences and emotions What she didn't know was that I thought my life was terribly boring and the last thing I wanted to do was to write about myself.**
  - `opus-mt`: Bu yüzden annem günlük deneyimlerimi ve duygularımı yazmanın bana iyi geleceğini düşündü. Bilmediği şey, hayatımın çok sıkıcı olduğu ve yapmak istediğim son şeyin kendim hakkında yazmak olduğuydu.
- **Instead, I began to write about people other than me and things that never really happened.**
  - `opus-mt`: Bunun yerine, benden başka insanlar ve gerçekte hiç olmamış şeyler hakkında yazmaya başladım.
- **And thus began my lifelong passion for writing fiction So from the very beginning, fiction for me was less of an autobiographical manifestation than a transcendental journey into other lives, other possibilities.**
  - `opus-mt`: Ve böylece benim yaşam boyu kurgu yazma tutkum başladı, yani en başından beri, benim için kurgu, otobiyografik bir tezahürden ziyade, diğer yaşamlara, diğer olasılıklara aşkın bir yolculuktu.
- **And please bear with me, I'll draw a circle and come back to this point Now one other thing happened around the same time.**
  - `opus-mt`: Ve lütfen bana katlanın, bir çember çizip bu noktaya geri döneceğim. Şimdi aynı zamanda başka bir şey daha oldu.
- **My mother became a diplomat.**
  - `opus-mt`: Annem diplomat oldu.
- **So from this small superstitious middle class neighborhood of my grandmother I was zoomed into this posh international school where I was the only Turk It was here that I had my first encounter with what I call as the representative foreigner.**
  - `opus-mt`: Bu yüzden büyükannemin bu küçük batıl inançlı orta sınıf mahallesinden, tek Türk olduğum bu havalı uluslararası okula yakınlaştırıldım. Temsili yabancı olarak adlandırdığım şeyle ilk karşılaşmam burada oldu.
