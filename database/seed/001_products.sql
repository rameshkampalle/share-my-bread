-- Share My Bread / sample product catalogue
-- Fixed IDs make Pinecone upserts and evaluation ground truth reproducible.

insert into public.products
  (id, sku, name, description, category, brand, unit, price, currency, aliases, dietary_tags, active)
values
('10000000-0000-0000-0000-000000000001','DAIRY-001','Plain Yogurt','Fresh unsweetened yogurt for breakfast, cooking and raita.','Dairy','Demo Fresh','500 g tub',2.49,'EUR',array['curd','dahi','yoghurt','fermented milk'],array['vegetarian','gluten-free'],true),
('10000000-0000-0000-0000-000000000002','DAIRY-002','Greek Yogurt','Thick strained yogurt with a creamy texture.','Dairy','Demo Fresh','450 g tub',3.19,'EUR',array['thick yogurt','strained yogurt','greek yoghurt'],array['vegetarian','gluten-free'],true),
('10000000-0000-0000-0000-000000000003','DAIRY-003','Whole Milk','Fresh full-fat dairy milk.','Dairy','Demo Fresh','1 litre carton',1.79,'EUR',array['full fat milk','dairy milk','volle melk'],array['vegetarian','gluten-free'],true),
('10000000-0000-0000-0000-000000000004','DAIRY-004','Buttermilk','Light cultured dairy drink suitable for cooking or drinking.','Dairy','Demo Fresh','1 litre carton',1.89,'EUR',array['chaas','cultured milk','karnemelk'],array['vegetarian','gluten-free'],true),
('10000000-0000-0000-0000-000000000005','DAIRY-005','Paneer','Fresh firm Indian cottage cheese suitable for curries and grilling.','Dairy','Demo Fresh','250 g pack',3.49,'EUR',array['indian cottage cheese','fresh cheese'],array['vegetarian','gluten-free'],true),
('10000000-0000-0000-0000-000000000006','DAIRY-006','Ghee','Clarified butter for frying and Indian cooking.','Dairy','Demo Pantry','300 g jar',5.99,'EUR',array['clarified butter','desi ghee'],array['vegetarian','gluten-free'],true),
('10000000-0000-0000-0000-000000000007','BAKERY-001','Whole Wheat Bread','Sliced whole-wheat loaf with a soft brown crumb.','Bakery','Demo Bakery','800 g loaf',2.29,'EUR',array['brown bread','wheat loaf','wholemeal bread'],array['vegetarian'],true),
('10000000-0000-0000-0000-000000000008','BAKERY-002','White Bread','Soft sliced white sandwich loaf.','Bakery','Demo Bakery','800 g loaf',1.89,'EUR',array['sandwich bread','white loaf'],array['vegetarian'],true),
('10000000-0000-0000-0000-000000000009','BAKERY-003','Multigrain Bread','Sliced loaf made with several grains and seeds.','Bakery','Demo Bakery','700 g loaf',2.79,'EUR',array['seed bread','mixed grain loaf'],array['vegetarian'],true),
('10000000-0000-0000-0000-000000000010','BAKERY-004','Croissants','Buttery flaky breakfast pastries.','Bakery','Demo Bakery','4 pack',3.25,'EUR',array['butter croissant','breakfast pastry'],array['vegetarian'],true),
('10000000-0000-0000-0000-000000000011','VEG-001','Eggplant','Fresh purple eggplant suitable for roasting and curry.','Vegetables','Demo Produce','1 piece',1.39,'EUR',array['brinjal','aubergine'],array['vegan','gluten-free'],true),
('10000000-0000-0000-0000-000000000012','VEG-002','Bell Pepper','Fresh sweet red bell pepper.','Vegetables','Demo Produce','1 piece',1.19,'EUR',array['capsicum','sweet pepper','paprika'],array['vegan','gluten-free'],true),
('10000000-0000-0000-0000-000000000013','VEG-003','Cilantro','Fresh green coriander leaves for garnish and cooking.','Vegetables','Demo Produce','50 g bunch',1.09,'EUR',array['coriander leaves','fresh coriander','dhaniya leaves'],array['vegan','gluten-free'],true),
('10000000-0000-0000-0000-000000000014','VEG-004','Zucchini','Fresh green summer squash.','Vegetables','Demo Produce','1 piece',0.99,'EUR',array['courgette'],array['vegan','gluten-free'],true),
('10000000-0000-0000-0000-000000000015','VEG-005','Tomatoes','Ripe red tomatoes for salad and cooking.','Vegetables','Demo Produce','500 g pack',2.19,'EUR',array['tomato','tamatar'],array['vegan','gluten-free'],true),
('10000000-0000-0000-0000-000000000016','VEG-006','Red Onions','Fresh red onions with a mild sharp flavour.','Vegetables','Demo Produce','1 kg bag',2.29,'EUR',array['onion','pyaz','uien'],array['vegan','gluten-free'],true),
('10000000-0000-0000-0000-000000000017','PULSE-001','Chickpeas','Dried chickpeas for curries, salads and hummus.','Pulses','Demo Pantry','500 g bag',1.99,'EUR',array['chana','garbanzo beans','kabuli chana'],array['vegan','gluten-free'],true),
('10000000-0000-0000-0000-000000000018','PULSE-002','Green Lentils','Dried whole green lentils for soups and dal.','Pulses','Demo Pantry','500 g bag',2.09,'EUR',array['lentils','green dal'],array['vegan','gluten-free'],true),
('10000000-0000-0000-0000-000000000019','PULSE-003','Red Lentils','Split red lentils that cook quickly.','Pulses','Demo Pantry','500 g bag',1.89,'EUR',array['masoor dal','red dal'],array['vegan','gluten-free'],true),
('10000000-0000-0000-0000-000000000020','PULSE-004','Kidney Beans','Red kidney beans for chilli and curries.','Pulses','Demo Pantry','400 g can',1.29,'EUR',array['rajma','red beans'],array['vegan','gluten-free'],true),
('10000000-0000-0000-0000-000000000021','BAKING-001','All-Purpose Flour','Refined wheat flour for baking and everyday cooking.','Baking','Demo Pantry','1 kg bag',1.69,'EUR',array['plain flour','maida','white flour'],array['vegetarian'],true),
('10000000-0000-0000-0000-000000000022','BAKING-002','Whole Wheat Flour','Whole-grain wheat flour for bread and flatbreads.','Baking','Demo Pantry','1 kg bag',1.89,'EUR',array['atta','wholemeal flour','chapati flour'],array['vegan'],true),
('10000000-0000-0000-0000-000000000023','FRUIT-001','Bananas','Ripe yellow bananas.','Fruit','Demo Produce','1 kg bunch',1.79,'EUR',array['banana','kela'],array['vegan','gluten-free'],true),
('10000000-0000-0000-0000-000000000024','FRUIT-002','Apples','Crisp sweet apples.','Fruit','Demo Produce','1 kg bag',2.49,'EUR',array['apple','appel'],array['vegan','gluten-free'],true),
('10000000-0000-0000-0000-000000000025','DRINK-001','Coconut Milk','Plant-based coconut milk for curries and desserts.','Drinks','Demo Pantry','400 ml can',1.59,'EUR',array['coconut cream drink','kokosmelk'],array['vegan','gluten-free','dairy-free'],true),
('10000000-0000-0000-0000-000000000026','DRINK-002','Oat Drink','Plant-based oat beverage for cereal and coffee.','Drinks','Demo Fresh','1 litre carton',2.09,'EUR',array['oat milk','havermelk'],array['vegan','dairy-free'],true),
('10000000-0000-0000-0000-000000000027','SNACK-001','Salted Potato Chips','Crispy salted potato chips.','Snacks','Demo Snacks','200 g bag',1.99,'EUR',array['crisps','chips','salted crisps'],array['vegan','gluten-free'],true),
('10000000-0000-0000-0000-000000000028','SNACK-002','Roasted Peanuts','Salted roasted peanuts.','Snacks','Demo Snacks','250 g bag',2.39,'EUR',array['groundnuts','moongfali'],array['vegan','gluten-free'],true),
('10000000-0000-0000-0000-000000000029','HOUSE-001','Dishwashing Liquid','Lemon-scented liquid for hand washing dishes.','Household','Demo Home','500 ml bottle',2.59,'EUR',array['dish soap','washing-up liquid','afwasmiddel'],array[]::text[],true),
('10000000-0000-0000-0000-000000000030','HOUSE-002','Kitchen Paper Towels','Absorbent paper towels for kitchen cleaning.','Household','Demo Home','2 rolls',3.29,'EUR',array['kitchen roll','paper towel'],array[]::text[],true)
on conflict (sku) do update set
  name = excluded.name,
  description = excluded.description,
  category = excluded.category,
  brand = excluded.brand,
  unit = excluded.unit,
  price = excluded.price,
  currency = excluded.currency,
  aliases = excluded.aliases,
  dietary_tags = excluded.dietary_tags,
  active = excluded.active,
  updated_at = timezone('utc', now());
