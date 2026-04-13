Original code is wrong  

<img width="695" height="215" alt="image" src="https://github.com/user-attachments/assets/8e47ff08-74d9-4386-b79f-274671066dbd" />  

Treat the entire bit string as a normal binary integer, convert it to a decimal number in one step, and then pad it with leading zeros on the left to reach the specified digit count.

Sample:  
p.357  
<img width="534" height="144" alt="image" src="https://github.com/user-attachments/assets/5586c73d-ef6c-4034-a233-e9fe956ea9ca" />   

Definition:  
TDS 2.3 §14.5.4 says Fixed-Length Numeric must decode the payload as N groups of 4 bits, one decimal digit per nibble.  
p.177-179  
<img width="772" height="199" alt="image" src="https://github.com/user-attachments/assets/cf791c97-e0b4-4b74-b46c-d8e2eca3b791" />  
<img width="799" height="497" alt="image" src="https://github.com/user-attachments/assets/dbcd0d8a-f2ea-47c9-82cd-195f1a8aedfc" />

